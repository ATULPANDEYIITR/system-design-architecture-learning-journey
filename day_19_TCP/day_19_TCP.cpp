/*
 * TCP: Connections, Handshake, Reliability, and Retransmission
 *
 * Industry-style case study:
 * A reliable file-transfer service built on top of a TCP connection.
 *
 * The program models:
 * - TCP connection establishment
 * - sequence and acknowledgment numbers
 * - segmentation
 * - cumulative acknowledgments
 * - packet loss
 * - retransmission
 * - timeout and exponential backoff
 * - sliding-window transmission
 * - receiver-side buffering
 * - application framing
 * - validation
 * - statistics
 * - complexity and resource considerations
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic tcp_case_study.cpp -o tcp_case_study
 */

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using SequenceNumber = std::uint64_t;

// -----------------------------------------------------------------------------
// Basic TCP-inspired data structures
// -----------------------------------------------------------------------------

enum class TcpState {
    Closed,
    Listen,
    SynSent,
    SynReceived,
    Established,
    FinWait1,
    FinWait2,
    CloseWait,
    LastAck,
    TimeWait
};

std::string stateName(TcpState state) {
    switch (state) {
        case TcpState::Closed: return "CLOSED";
        case TcpState::Listen: return "LISTEN";
        case TcpState::SynSent: return "SYN-SENT";
        case TcpState::SynReceived: return "SYN-RECEIVED";
        case TcpState::Established: return "ESTABLISHED";
        case TcpState::FinWait1: return "FIN-WAIT-1";
        case TcpState::FinWait2: return "FIN-WAIT-2";
        case TcpState::CloseWait: return "CLOSE-WAIT";
        case TcpState::LastAck: return "LAST-ACK";
        case TcpState::TimeWait: return "TIME-WAIT";
    }

    return "UNKNOWN";
}

struct Segment {
    SequenceNumber sequence;
    std::string payload;
    bool retransmission{false};

    SequenceNumber endSequence() const {
        return sequence + payload.size();
    }
};

struct Ack {
    SequenceNumber acknowledgment;
};

// -----------------------------------------------------------------------------
// TCP connection establishment
// -----------------------------------------------------------------------------

class TcpHandshake {
private:
    SequenceNumber clientIsn_;
    SequenceNumber serverIsn_;

public:
    TcpHandshake(SequenceNumber clientIsn, SequenceNumber serverIsn)
        : clientIsn_(clientIsn), serverIsn_(serverIsn) {}

    void run() const {
        std::cout << "\n=== THREE-WAY HANDSHAKE ===\n";

        std::cout
            << "Client -> Server: SYN "
            << "SEQ=" << clientIsn_ << '\n';

        std::cout
            << "Server -> Client: SYN+ACK "
            << "SEQ=" << serverIsn_
            << " ACK=" << clientIsn_ + 1 << '\n';

        std::cout
            << "Client -> Server: ACK "
            << "SEQ=" << clientIsn_ + 1
            << " ACK=" << serverIsn_ + 1 << '\n';

        std::cout << "Connection state: ESTABLISHED\n";
    }
};

// -----------------------------------------------------------------------------
// Receiver with out-of-order buffering
// -----------------------------------------------------------------------------

class TcpReceiver {
private:
    SequenceNumber expected_;
    std::string delivered_;
    std::map<SequenceNumber, std::string> buffered_;

public:
    explicit TcpReceiver(SequenceNumber initialSequence)
        : expected_(initialSequence) {}

    Ack receive(const Segment& segment) {
        if (segment.sequence < expected_) {
            // Duplicate data. Return the current cumulative ACK.
            return {expected_};
        }

        if (segment.sequence == expected_) {
            delivered_ += segment.payload;
            expected_ = segment.endSequence();

            // Release buffered segments once the missing gap is filled.
            while (true) {
                auto it = buffered_.find(expected_);

                if (it == buffered_.end()) {
                    break;
                }

                delivered_ += it->second;
                expected_ += it->second.size();
                buffered_.erase(it);
            }

            return {expected_};
        }

        // A future segment has arrived before a missing segment.
        // Buffer it and acknowledge the first missing byte.
        buffered_.emplace(segment.sequence, segment.payload);

        return {expected_};
    }

    const std::string& data() const {
        return delivered_;
    }

    SequenceNumber expectedSequence() const {
        return expected_;
    }
};

// -----------------------------------------------------------------------------
// RTT/RTO estimation
// -----------------------------------------------------------------------------

class RttEstimator {
private:
    double srtt_{0.0};
    double rttvar_{0.0};
    double rto_{0.0};
    bool initialized_{false};

public:
    void update(double measuredRtt) {
        if (measuredRtt <= 0.0) {
            throw std::invalid_argument("RTT must be positive.");
        }

        constexpr double alpha = 1.0 / 8.0;
        constexpr double beta = 1.0 / 4.0;

        if (!initialized_) {
            srtt_ = measuredRtt;
            rttvar_ = measuredRtt / 2.0;
            initialized_ = true;
        } else {
            rttvar_ =
                (1.0 - beta) * rttvar_ +
                beta * std::abs(srtt_ - measuredRtt);

            srtt_ =
                (1.0 - alpha) * srtt_ +
                alpha * measuredRtt;
        }

        rto_ = srtt_ + 4.0 * rttvar_;

        // A practical implementation also applies protocol-specific bounds.
        rto_ = std::max(rto_, 0.001);
    }

    double srtt() const { return srtt_; }
    double rttvar() const { return rttvar_; }
    double rto() const { return rto_; }
};

// -----------------------------------------------------------------------------
// Congestion-control model
// -----------------------------------------------------------------------------

class CongestionController {
private:
    double cwnd_{1.0};
    double ssthresh_{16.0};

public:
    void acknowledge() {
        if (cwnd_ < ssthresh_) {
            // Simplified slow-start behavior.
            cwnd_ += 1.0;
        } else {
            // Simplified congestion avoidance.
            cwnd_ += 1.0 / std::max(cwnd_, 1.0);
        }
    }

    void timeout() {
        ssthresh_ = std::max(cwnd_ / 2.0, 2.0);
        cwnd_ = 1.0;
    }

    void duplicateAckLoss() {
        ssthresh_ = std::max(cwnd_ / 2.0, 2.0);
        cwnd_ = ssthresh_;
    }

    double cwnd() const { return cwnd_; }
    double ssthresh() const { return ssthresh_; }
};

// -----------------------------------------------------------------------------
// Sliding-window sender
// -----------------------------------------------------------------------------

class SlidingWindowSender {
private:
    SequenceNumber base_;
    SequenceNumber nextSequence_;
    std::size_t windowSize_;

public:
    SlidingWindowSender(
        SequenceNumber initialSequence,
        std::size_t windowSize
    )
        : base_(initialSequence),
          nextSequence_(initialSequence),
          windowSize_(windowSize) {
        if (windowSize == 0) {
            throw std::invalid_argument("Window size must be positive.");
        }
    }

    bool canSend() const {
        return nextSequence_ < base_ + windowSize_;
    }

    SequenceNumber send() {
        if (!canSend()) {
            throw std::runtime_error("Transmission window is full.");
        }

        return nextSequence_++;
    }

    void acknowledge(SequenceNumber acknowledgment) {
        if (acknowledgment < base_) {
            // Old duplicate ACK.
            return;
        }

        if (acknowledgment > nextSequence_) {
            throw std::invalid_argument("ACK exceeds transmitted sequence space.");
        }

        base_ = acknowledgment;
    }

    SequenceNumber base() const {
        return base_;
    }
};

// -----------------------------------------------------------------------------
// Application-level framing
// -----------------------------------------------------------------------------

std::string encodeFrame(const std::string& message) {
    if (message.size() > 0xFFFFFFFFULL) {
        throw std::length_error("Message exceeds 32-bit frame length.");
    }

    std::uint32_t length = static_cast<std::uint32_t>(message.size());

    std::string frame(4, '\0');

    frame[0] = static_cast<char>((length >> 24) & 0xFF);
    frame[1] = static_cast<char>((length >> 16) & 0xFF);
    frame[2] = static_cast<char>((length >> 8) & 0xFF);
    frame[3] = static_cast<char>(length & 0xFF);

    frame += message;
    return frame;
}

std::vector<std::string> decodeFrames(
    std::string& receiveBuffer,
    std::size_t maximumFrameSize
) {
    std::vector<std::string> frames;

    while (receiveBuffer.size() >= 4) {
        const auto byte = [](char c) {
            return static_cast<std::uint32_t>(
                static_cast<unsigned char>(c)
            );
        };

        std::uint32_t length =
            (byte(receiveBuffer[0]) << 24) |
            (byte(receiveBuffer[1]) << 16) |
            (byte(receiveBuffer[2]) << 8) |
            byte(receiveBuffer[3]);

        if (length > maximumFrameSize) {
            throw std::runtime_error("Frame exceeds configured maximum.");
        }

        if (receiveBuffer.size() < 4ULL + length) {
            break;
        }

        frames.push_back(receiveBuffer.substr(4, length));
        receiveBuffer.erase(0, 4ULL + length);
    }

    return frames;
}

// -----------------------------------------------------------------------------
// Reliable file-transfer case study
// -----------------------------------------------------------------------------

class ReliableFileTransfer {
private:
    std::string data_;
    std::size_t segmentSize_;
    double lossProbability_;
    std::mt19937 randomEngine_;
    std::uniform_real_distribution<double> distribution_;

    TcpReceiver receiver_;

    std::size_t totalTransmissions_{0};
    std::size_t retransmissions_{0};

    RttEstimator rttEstimator_;

public:
    ReliableFileTransfer(
        std::string data,
        std::size_t segmentSize,
        double lossProbability,
        std::uint32_t seed
    )
        : data_(std::move(data)),
          segmentSize_(segmentSize),
          lossProbability_(lossProbability),
          randomEngine_(seed),
          distribution_(0.0, 1.0),
          receiver_(0) {
        if (segmentSize_ == 0) {
            throw std::invalid_argument("Segment size must be positive.");
        }

        if (lossProbability_ < 0.0 || lossProbability_ > 1.0) {
            throw std::invalid_argument(
                "Loss probability must be between zero and one."
            );
        }
    }

    bool networkLosesSegment() {
        return distribution_(randomEngine_) < lossProbability_;
    }

    void transmitSegment(
        SequenceNumber sequence,
        const std::string& payload
    ) {
        bool acknowledged = false;
        std::size_t attempts = 0;

        while (!acknowledged) {
            ++attempts;
            ++totalTransmissions_;

            const bool retransmission = attempts > 1;

            if (retransmission) {
                ++retransmissions_;
            }

            Segment segment{
                sequence,
                payload,
                retransmission
            };

            if (networkLosesSegment()) {
                std::cout
                    << "LOSS       seq=" << segment.sequence
                    << " len=" << segment.payload.size()
                    << " attempt=" << attempts << '\n';

                // A real TCP sender starts or continues a retransmission
                // strategy. Here we model timeout-driven retransmission.
                continue;
            }

            Ack acknowledgment = receiver_.receive(segment);

            std::cout
                << "DELIVERED  seq=" << segment.sequence
                << " len=" << segment.payload.size()
                << " ACK=" << acknowledgment.acknowledgment
                << " retransmission="
                << std::boolalpha << retransmission << '\n';

            acknowledged =
                acknowledgment.acknowledgment >= segment.endSequence();
        }
    }

    void run() {
        std::cout << "\n=== RELIABLE FILE TRANSFER ===\n";
        std::cout << "Data size: " << data_.size() << " bytes\n";
        std::cout << "Segment size: " << segmentSize_ << " bytes\n";
        std::cout << "Simulated loss probability: "
                  << lossProbability_ << '\n';

        // The case study uses a simple stop-and-wait mechanism for each
        // segment so that retransmission is easy to observe. TCP itself
        // normally uses a sliding window and can have many segments in flight.
        for (std::size_t offset = 0; offset < data_.size(); offset += segmentSize_) {
            std::size_t length =
                std::min(segmentSize_, data_.size() - offset);

            transmitSegment(
                static_cast<SequenceNumber>(offset),
                data_.substr(offset, length)
            );
        }

        std::cout << "\nTransfer complete.\n";
        std::cout << "Original bytes: "
                  << data_.size() << '\n';
        std::cout << "Received bytes: "
                  << receiver_.data().size() << '\n';
        std::cout << "Total transmissions: "
                  << totalTransmissions_ << '\n';
        std::cout << "Retransmissions: "
                  << retransmissions_ << '\n';

        if (receiver_.data() != data_) {
            throw std::runtime_error(
                "Reliability invariant failed: received data differs."
            );
        }

        std::cout << "Integrity check: PASS\n";
    }

    RttEstimator& rttEstimator() {
        return rttEstimator_;
    }
};

// -----------------------------------------------------------------------------
// Demonstrations
// -----------------------------------------------------------------------------

void demonstrateRtt() {
    std::cout << "\n=== RTT/RTO ESTIMATION ===\n";

    RttEstimator estimator;

    for (double sample : {0.100, 0.120, 0.090, 0.200, 0.150}) {
        estimator.update(sample);

        std::cout
            << std::fixed << std::setprecision(3)
            << "RTT=" << sample
            << " SRTT=" << estimator.srtt()
            << " RTTVAR=" << estimator.rttvar()
            << " RTO=" << estimator.rto()
            << '\n';
    }
}

void demonstrateSlidingWindow() {
    std::cout << "\n=== SLIDING WINDOW ===\n";

    SlidingWindowSender sender(1000, 4);

    while (sender.canSend()) {
        std::cout << "Sent sequence " << sender.send() << '\n';
    }

    std::cout << "Window full: " << std::boolalpha
              << !sender.canSend() << '\n';

    sender.acknowledge(1002);

    std::cout << "ACK=1002, new base="
              << sender.base() << '\n';

    std::cout << "New sequence sent="
              << sender.send() << '\n';
}

void demonstrateCongestionControl() {
    std::cout << "\n=== CONGESTION CONTROL ===\n";

    CongestionController controller;

    for (int i = 0; i < 8; ++i) {
        controller.acknowledge();

        std::cout
            << "ACK "
            << i + 1
            << ": cwnd=" << controller.cwnd()
            << " ssthresh=" << controller.ssthresh()
            << '\n';
    }

    controller.duplicateAckLoss();

    std::cout
        << "Triple duplicate ACK: cwnd="
        << controller.cwnd()
        << " ssthresh="
        << controller.ssthresh()
        << '\n';

    controller.timeout();

    std::cout
        << "Timeout: cwnd="
        << controller.cwnd()
        << " ssthresh="
        << controller.ssthresh()
        << '\n';
}

void demonstrateOutOfOrderDelivery() {
    std::cout << "\n=== OUT-OF-ORDER DELIVERY ===\n";

    TcpReceiver receiver(1000);

    std::vector<Segment> segments{
        {1000, "ABC", false},
        {1006, "GHI", false},
        {1003, "DEF", false}
    };

    for (const auto& segment : segments) {
        Ack ack = receiver.receive(segment);

        std::cout
            << "Segment seq=" << segment.sequence
            << " payload=" << segment.payload
            << " -> ACK=" << ack.acknowledgment
            << '\n';
    }

    std::cout
        << "Reconstructed stream: "
        << receiver.data() << '\n';
}

void demonstrateFraming() {
    std::cout << "\n=== APPLICATION FRAMING ===\n";

    std::string wireBuffer;

    wireBuffer += encodeFrame("first");
    wireBuffer += encodeFrame("second");
    wireBuffer += encodeFrame("third");

    // Simulate fragmented TCP reads.
    std::string receiveBuffer;

    for (std::size_t offset = 0; offset < wireBuffer.size();) {
        const std::size_t chunkSize =
            std::min<std::size_t>(3, wireBuffer.size() - offset);

        receiveBuffer.append(wireBuffer, offset, chunkSize);
        offset += chunkSize;

        auto frames = decodeFrames(receiveBuffer, 1024);

        for (const auto& frame : frames) {
            std::cout << "Application message: " << frame << '\n';
        }
    }
}

void explainArchitecture() {
    std::cout << "\n=== ARCHITECTURE ===\n";
    std::cout
        << "Application protocol\n"
        << "        |\n"
        << "        v\n"
        << "TCP byte stream\n"
        << "        |\n"
        << "        v\n"
        << "IP packet delivery\n"
        << "        |\n"
        << "        v\n"
        << "Link/network infrastructure\n";

    std::cout
        << "\nThe application should not reimplement TCP reliability when it is "
        << "already using a normal TCP socket. The case study models TCP "
        << "internals educationally, while the operating system normally "
        << "implements those mechanisms in the kernel networking stack.\n";
}

void explainComplexity() {
    std::cout << "\n=== COMPLEXITY AND PERFORMANCE ===\n";

    std::cout
        << "Segment generation: O(n) for n bytes.\n"
        << "Sequential delivery: O(n) in the normal case.\n"
        << "Out-of-order lookup: O(log k) with std::map for k buffered segments.\n"
        << "Buffered memory: O(k) for k out-of-order segments.\n"
        << "Retransmissions increase network work beyond O(n) under loss.\n"
        << "A large congestion window can improve throughput on high-bandwidth "
           "paths but increases outstanding data and loss exposure.\n";
}

void explainFailureConditions() {
    std::cout << "\n=== FAILURE CONDITIONS ===\n";

    std::cout
        << "Connection establishment can fail because the peer is unavailable.\n"
        << "Segments can be lost or corrupted.\n"
        << "The receiver can advertise a small or zero receive window.\n"
        << "Congestion can trigger loss and reduction of the sending rate.\n"
        << "A connection can be reset unexpectedly.\n"
        << "Applications can close sockets while data is still being processed.\n"
        << "Resource exhaustion can occur when too many connections or buffers "
           "are maintained.\n";
}

void explainSecurity() {
    std::cout << "\n=== SECURITY ===\n";

    std::cout
        << "TCP provides transport reliability, not confidentiality.\n"
        << "TLS should be used when application data must be encrypted.\n"
        << "SYN floods can exhaust server resources during connection setup.\n"
        << "Firewalls can enforce connection and traffic policies.\n"
        << "Application authentication and authorization remain necessary.\n"
        << "Frame lengths must be validated before allocating memory.\n"
        << "Idle connections should have appropriate resource and timeout limits.\n";
}

// -----------------------------------------------------------------------------
// Main
// -----------------------------------------------------------------------------

int main() {
    try {
        std::cout << "TCP CONNECTION, RELIABILITY, AND RETRANSMISSION CASE STUDY\n";

        explainArchitecture();

        TcpHandshake handshake(10000, 50000);
        handshake.run();

        demonstrateRtt();
        demonstrateOutOfOrderDelivery();
        demonstrateSlidingWindow();
        demonstrateCongestionControl();
        demonstrateFraming();

        ReliableFileTransfer transfer(
            "TCP reliably delivers an ordered byte stream even when the "
            "underlying network experiences controlled packet loss.",
            12,
            0.30,
            42
        );

        transfer.rttEstimator().update(0.100);
        transfer.rttEstimator().update(0.120);

        std::cout
            << "\nEstimated RTO before transfer: "
            << transfer.rttEstimator().rto()
            << " seconds\n";

        transfer.run();

        explainComplexity();
        explainFailureConditions();
        explainSecurity();

        std::cout << "\n=== CONNECTION TERMINATION ===\n";
        std::cout
            << "FIN -> ACK -> FIN -> ACK\n"
            << "The full-duplex TCP connection can close each direction "
               "independently. TIME-WAIT protects against delayed old "
               "segments and supports retransmission of the final ACK.\n";

        return 0;
    }
    catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }
}
