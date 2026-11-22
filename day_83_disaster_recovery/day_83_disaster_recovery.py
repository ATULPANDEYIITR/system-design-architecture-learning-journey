#!/usr/bin/env python3
"""
Disaster Recovery Management System
Domain: Backup, Restore, Recovery Point Objective (RPO),
Recovery Time Objective (RTO), and Business Continuity.

Python 3.10+
Standard-library only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import time
import uuid

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("disaster-recovery")


class BackupType(Enum):
    FULL = "FULL"
    INCREMENTAL = "INCREMENTAL"
    DIFFERENTIAL = "DIFFERENTIAL"


class BackupStatus(Enum):
    CREATED = "CREATED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    RESTORED = "RESTORED"


class RecoveryStatus(Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class IncidentSeverity(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class RecoveryPolicy:
    name: str
    rpo_minutes: int
    rto_minutes: int
    retention_days: int
    require_offsite_backup: bool = True
    require_integrity_check: bool = True
    allowed_backup_types: tuple = (
        BackupType.FULL,
        BackupType.INCREMENTAL,
        BackupType.DIFFERENTIAL,
    )

    def __post_init__(self):
        if self.rpo_minutes < 0:
            raise ValueError("RPO cannot be negative")
        if self.rto_minutes <= 0:
            raise ValueError("RTO must be positive")
        if self.retention_days <= 0:
            raise ValueError("Retention must be positive")


@dataclass
class Backup:
    backup_id: str
    system_name: str
    backup_type: BackupType
    created_at: datetime
    data: dict
    checksum: str
    offsite: bool
    status: BackupStatus
    parent_backup_id: Optional[str] = None
    size_bytes: int = 0

    @staticmethod
    def calculate_checksum(data: dict) -> str:
        serialized = json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":")
        ).encode("utf-8")

        return hashlib.sha256(serialized).hexdigest()

    def verify_integrity(self) -> bool:
        return self.checksum == self.calculate_checksum(self.data)


@dataclass
class DisasterIncident:
    incident_id: str
    system_name: str
    severity: IncidentSeverity
    occurred_at: datetime
    description: str
    status: RecoveryStatus = RecoveryStatus.PENDING


@dataclass
class RecoveryResult:
    incident_id: str
    backup_id: str
    recovery_started: datetime
    recovery_completed: datetime
    data_recovery_point: datetime
    actual_rpo_minutes: float
    actual_rto_minutes: float
    rpo_met: bool
    rto_met: bool
    success: bool


@dataclass
class ProtectedSystem:
    name: str
    current_data: dict = field(default_factory=dict)
    last_modified: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    policy: Optional[RecoveryPolicy] = None


class DisasterRecoveryManager:

    def __init__(self, storage_directory: Optional[str] = None):
        self.storage = Path(
            storage_directory or tempfile.mkdtemp(
                prefix="disaster_recovery_"
            )
        )

        self.storage.mkdir(parents=True, exist_ok=True)

        self.systems: dict[str, ProtectedSystem] = {}
        self.backups: dict[str, Backup] = {}
        self.incidents: dict[str, DisasterIncident] = {}
        self.recovery_results: list[RecoveryResult] = []

    def register_system(
        self,
        name: str,
        initial_data: dict,
        policy: RecoveryPolicy
    ) -> ProtectedSystem:

        if not name.strip():
            raise ValueError("System name cannot be empty")

        if name in self.systems:
            raise ValueError("System already registered")

        system = ProtectedSystem(
            name=name,
            current_data=initial_data.copy(),
            policy=policy
        )

        self.systems[name] = system
        logger.info("Registered protected system: %s", name)

        return system

    def update_system(self, name: str, updates: dict):
        system = self._get_system(name)

        if not isinstance(updates, dict):
            raise TypeError("Updates must be a dictionary")

        system.current_data.update(updates)
        system.last_modified = datetime.now(timezone.utc)

        logger.info("Updated system: %s", name)

    def _get_system(self, name: str) -> ProtectedSystem:
        if name not in self.systems:
            raise KeyError(f"Unknown system: {name}")

        return self.systems[name]

    def create_backup(
        self,
        system_name: str,
        backup_type: BackupType,
        offsite: bool = True
    ) -> Backup:

        system = self._get_system(system_name)
        policy = system.policy

        if backup_type not in policy.allowed_backup_types:
            raise ValueError("Backup type prohibited by recovery policy")

        if policy.require_offsite_backup and not offsite:
            raise ValueError("Offsite backup is mandatory")

        parent_id = None
        backup_data = system.current_data.copy()

        if backup_type == BackupType.INCREMENTAL:
            previous = self._latest_verified_backup(system_name)

            if previous is None:
                raise ValueError(
                    "Incremental backup requires a previous verified backup"
                )

            parent_id = previous.backup_id

        serialized = json.dumps(
            backup_data,
            sort_keys=True,
            separators=(",", ":")
        ).encode("utf-8")

        backup_id = str(uuid.uuid4())

        backup = Backup(
            backup_id=backup_id,
            system_name=system_name,
            backup_type=backup_type,
            created_at=datetime.now(timezone.utc),
            data=backup_data,
            checksum=Backup.calculate_checksum(backup_data),
            offsite=offsite,
            status=BackupStatus.CREATED,
            parent_backup_id=parent_id,
            size_bytes=len(serialized)
        )

        self.backups[backup_id] = backup

        self._persist_backup(backup)

        if policy.require_integrity_check:
            self.verify_backup(backup_id)

        logger.info(
            "Backup created: %s | type=%s",
            backup_id,
            backup_type.value
        )

        return backup

    def _persist_backup(self, backup: Backup):
        """
        Write backup metadata and data using atomic file replacement.

        Production systems should encrypt backup contents and use
        immutable, independently authenticated storage.
        """
        destination = self.storage / f"{backup.backup_id}.json"
        temporary = destination.with_suffix(".tmp")

        payload = {
            "backup_id": backup.backup_id,
            "system_name": backup.system_name,
            "backup_type": backup.backup_type.value,
            "created_at": backup.created_at.isoformat(),
            "data": backup.data,
            "checksum": backup.checksum,
            "offsite": backup.offsite,
            "parent_backup_id": backup.parent_backup_id,
            "size_bytes": backup.size_bytes,
        }

        try:
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(payload, file, sort_keys=True)
                file.flush()

            temporary.replace(destination)

        except OSError:
            temporary.unlink(missing_ok=True)
            raise

    def verify_backup(self, backup_id: str) -> bool:
        backup = self._get_backup(backup_id)

        if not backup.verify_integrity():
            backup.status = BackupStatus.FAILED
            raise ValueError("Backup integrity verification failed")

        backup.status = BackupStatus.VERIFIED

        logger.info("Backup verified: %s", backup_id)

        return True

    def _get_backup(self, backup_id: str) -> Backup:
        if backup_id not in self.backups:
            raise KeyError(f"Backup not found: {backup_id}")

        return self.backups[backup_id]

    def _latest_verified_backup(
        self,
        system_name: str
    ) -> Optional[Backup]:

        candidates = [
            backup
            for backup in self.backups.values()
            if backup.system_name == system_name
            and backup.status == BackupStatus.VERIFIED
        ]

        return max(
            candidates,
            key=lambda item: item.created_at,
            default=None
        )

    def list_backups(self, system_name: str) -> list[Backup]:
        self._get_system(system_name)

        return sorted(
            [
                backup
                for backup in self.backups.values()
                if backup.system_name == system_name
            ],
            key=lambda item: item.created_at
        )

    def create_incident(
        self,
        system_name: str,
        severity: IncidentSeverity,
        description: str,
        occurred_at: Optional[datetime] = None
    ) -> DisasterIncident:

        self._get_system(system_name)

        incident = DisasterIncident(
            incident_id=str(uuid.uuid4()),
            system_name=system_name,
            severity=severity,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            description=description
        )

        if incident.occurred_at.tzinfo is None:
            raise ValueError("Incident timestamp must be timezone-aware")

        self.incidents[incident.incident_id] = incident

        logger.warning(
            "Disaster incident registered: %s",
            incident.incident_id
        )

        return incident

    def restore(
        self,
        incident_id: str,
        backup_id: Optional[str] = None
    ) -> RecoveryResult:

        if incident_id not in self.incidents:
            raise KeyError("Incident not found")

        incident = self.incidents[incident_id]
        system = self._get_system(incident.system_name)

        if incident.status != RecoveryStatus.PENDING:
            raise ValueError("Incident has already been processed")

        candidates = self.list_backups(system.name)

        if backup_id is not None:
            candidates = [
                item for item in candidates
                if item.backup_id == backup_id
            ]

        eligible = [
            item for item in candidates
            if item.status == BackupStatus.VERIFIED
            and item.created_at <= incident.occurred_at
            and (
                not system.policy.require_offsite_backup
                or item.offsite
            )
        ]

        if not eligible:
            incident.status = RecoveryStatus.FAILED
            raise RuntimeError("No eligible verified backup exists")

        selected = max(
            eligible,
            key=lambda item: item.created_at
        )

        incident.status = RecoveryStatus.IN_PROGRESS

        started = datetime.now(timezone.utc)

        try:
            if not selected.verify_integrity():
                raise ValueError("Backup checksum mismatch")

            # Stage restored data before replacing active application state.
            restored_data = selected.data.copy()

            if not isinstance(restored_data, dict):
                raise ValueError("Invalid restored data structure")

            system.current_data = restored_data
            system.last_modified = selected.created_at

            selected.status = BackupStatus.RESTORED
            incident.status = RecoveryStatus.SUCCESS

        except Exception:
            incident.status = RecoveryStatus.FAILED
            raise

        completed = datetime.now(timezone.utc)

        actual_rpo = max(
            0.0,
            (incident.occurred_at - selected.created_at).total_seconds()
            / 60
        )

        actual_rto = max(
            0.0,
            (completed - started).total_seconds() / 60
        )

        result = RecoveryResult(
            incident_id=incident_id,
            backup_id=selected.backup_id,
            recovery_started=started,
            recovery_completed=completed,
            data_recovery_point=selected.created_at,
            actual_rpo_minutes=actual_rpo,
            actual_rto_minutes=actual_rto,
            rpo_met=actual_rpo <= system.policy.rpo_minutes,
            rto_met=actual_rto <= system.policy.rto_minutes,
            success=True
        )

        self.recovery_results.append(result)

        logger.info(
            "Restore completed | RPO %.2f minutes | RTO %.2f minutes",
            actual_rpo,
            actual_rto
        )

        return result

    def recovery_report(self) -> dict:
        total = len(self.recovery_results)

        if total == 0:
            return {
                "total_recoveries": 0,
                "successful_recoveries": 0,
                "rpo_compliance_percent": 0.0,
                "rto_compliance_percent": 0.0
            }

        successful = [
            result
            for result in self.recovery_results
            if result.success
        ]

        return {
            "total_recoveries": total,
            "successful_recoveries": len(successful),
            "rpo_compliance_percent": round(
                100 * sum(item.rpo_met for item in successful)
                / len(successful),
                2
            ),
            "rto_compliance_percent": round(
                100 * sum(item.rto_met for item in successful)
                / len(successful),
                2
            ),
            "average_actual_rpo_minutes": round(
                sum(item.actual_rpo_minutes for item in successful)
                / len(successful),
                3
            ),
            "average_actual_rto_minutes": round(
                sum(item.actual_rto_minutes for item in successful)
                / len(successful),
                3
            )
        }

    def enforce_retention(self, system_name: str) -> int:
        system = self._get_system(system_name)

        cutoff = (
            datetime.now(timezone.utc)
            - timedelta(days=system.policy.retention_days)
        )

        deleted = 0

        for backup in list(self.backups.values()):
            if (
                backup.system_name == system_name
                and backup.created_at < cutoff
            ):
                path = self.storage / f"{backup.backup_id}.json"
                path.unlink(missing_ok=True)
                del self.backups[backup.backup_id]
                deleted += 1

        return deleted

    def export_report(self, filename: str):
        """
        Export recovery metrics without exposing backup payloads.
        """
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metrics": self.recovery_report(),
            "backup_count": len(self.backups),
            "incident_count": len(self.incidents)
        }

        destination = Path(filename)
        temporary = destination.with_suffix(destination.suffix + ".tmp")

        try:
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(report, file, indent=2)
                file.flush()

            temporary.replace(destination)

        except OSError:
            temporary.unlink(missing_ok=True)
            raise


def demonstrate_disaster_recovery():
    with tempfile.TemporaryDirectory() as directory:
        manager = DisasterRecoveryManager(directory)

        policy = RecoveryPolicy(
            name="Critical Banking Database",
            rpo_minutes=15,
            rto_minutes=30,
            retention_days=30,
            require_offsite_backup=True,
            require_integrity_check=True
        )

        manager.register_system(
            "banking-db",
            {
                "account_1001": 50000,
                "account_1002": 75000,
                "currency": "INR",
                "transactions": 1200
            },
            policy
        )

        first_backup = manager.create_backup(
            "banking-db",
            BackupType.FULL
        )

        manager.update_system(
            "banking-db",
            {
                "account_1001": 55000,
                "transactions": 1201
            }
        )

        second_backup = manager.create_backup(
            "banking-db",
            BackupType.INCREMENTAL
        )

        # An incident occurring after the second backup.
        incident_time = (
            second_backup.created_at + timedelta(minutes=5)
        )

        incident = manager.create_incident(
            "banking-db",
            IncidentSeverity.CRITICAL,
            "Primary database storage failure",
            occurred_at=incident_time
        )

        # Simulate data loss after the incident.
        manager.update_system(
            "banking-db",
            {
                "account_1001": 0,
                "transactions": 0
            }
        )

        result = manager.restore(
            incident.incident_id,
            second_backup.backup_id
        )

        assert result.success
        assert result.rpo_met
        assert manager.systems["banking-db"].current_data[
            "account_1001"
        ] == 55000

        assert first_backup.verify_integrity()

        print("\nRESTORED DATABASE")
        print(json.dumps(
            manager.systems["banking-db"].current_data,
            indent=2
        ))

        print("\nRECOVERY RESULT")
        print(json.dumps(asdict(result), default=str, indent=2))

        print("\nRECOVERY REPORT")
        print(json.dumps(
            manager.recovery_report(),
            indent=2
        ))

        manager.export_report(
            str(Path(directory) / "recovery-report.json")
        )


if __name__ == "__main__":
    demonstrate_disaster_recovery()
