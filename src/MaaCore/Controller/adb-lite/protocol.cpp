#include <iomanip>
#include <iostream>
#include <boost/asio/read.hpp>
#include <boost/asio/write.hpp>

#include "protocol.hpp"

using boost::asio::ip::tcp;

namespace adb::protocol
{
/// Encoded the ADB host request.
/**
 * @param body Body of the request.
 * @return Encoded request.
 */
static inline std::string host_request(const std::string_view body)
{
    std::stringstream ss;
    ss << std::setfill('0') << std::setw(4) << std::hex << body.size() << body;
    return ss.str();
}

/// Receive and check the response.
/**
 * @param socket Opened adb connection.
 * @param failure Error message if the response is not OKAY.
 * @return `true` if the response is OKAY, `false` otherwise.
 * @throw std::runtime_error Thrown on socket failure
 */
static inline bool host_response(tcp::socket& socket, std::string& failure)
{
    std::array<char, 4> header;
    boost::asio::read(socket, boost::asio::buffer(header));
    const auto result = std::string_view(header.data(), 4);
    if (result == "OKAY") {
        return true;
    }

    if (result != "FAIL") {
        failure = "unknown response";
        return false;
    }

    failure = host_message(socket);
    return false;
}

std::string host_message(tcp::socket& socket)
{
    std::array<char, 4> header;
    boost::asio::read(socket, boost::asio::buffer(header));
    auto remain = std::stoull(std::string(header.data(), 4), nullptr, 16);

    std::string message;
    std::array<char, 64 * 1024> buffer;
    while (remain > 0) {
        const auto length = socket.read_some(boost::asio::buffer(buffer.data(), (std::min)(remain, buffer.size())));
        message.append(buffer.data(), length);
        remain -= length;
    }

    return message;
}

std::string host_data(tcp::socket& socket)
{
    std::string data;
    std::array<char, 64 * 1024> buffer;
    boost::system::error_code ec;

    while (!ec) {
        const auto length = socket.read_some(boost::asio::buffer(buffer), ec);
        data.append(buffer.data(), length);
        if (ec == boost::asio::error::eof) {
            break;
        }
        if (ec) throw boost::system::system_error(ec);
    }

    return data;
}

std::string sync_request(const std::string_view id, const uint32_t length)
{
    const auto len = {
        static_cast<char>(length & 0xff),
        static_cast<char>((length >> 8) & 0xff),
        static_cast<char>((length >> 16) & 0xff),
        static_cast<char>((length >> 24) & 0xff),
    };

    return std::string(id) + std::string(len.begin(), len.end());
}

void sync_response(tcp::socket& socket, std::string& id, uint32_t& length)
{
    std::array<char, 8> response;
    boost::asio::read(socket, boost::asio::buffer(response));

    id = std::string(response.data(), 4);
    length = static_cast<uint32_t>(static_cast<unsigned char>(response[4])) |
             (static_cast<uint32_t>(static_cast<unsigned char>(response[5])) << 8) |
             (static_cast<uint32_t>(static_cast<unsigned char>(response[6])) << 16) |
             (static_cast<uint32_t>(static_cast<unsigned char>(response[7])) << 24);
}

void send_host_request(tcp::socket& socket, const std::string_view request)
{
    boost::asio::write(socket, boost::asio::buffer(protocol::host_request(request)));
    std::string failure;
    if (!protocol::host_response(socket, failure)) {
        throw std::runtime_error(failure);
    }
}

void send_sync_request(tcp::socket& socket, const std::string_view id, uint32_t length, const char* body)
{
    auto data_request = protocol::sync_request(id, length);
    boost::asio::write(socket, boost::asio::buffer(data_request));
    boost::asio::write(socket, boost::asio::buffer(body, length));
}
} // namespace adb::protocol
