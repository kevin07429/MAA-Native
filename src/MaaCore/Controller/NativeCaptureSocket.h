#pragma once

#include <array>
#include <chrono>
#include <optional>
#include <string>
#include <boost/asio.hpp>

namespace asst::native_capture
{
// One request produces one fresh frame. All asynchronous operations are drained
// before returning, including cancellation, so buffers cannot outlive their IO.
inline std::optional<std::string> read_frame(unsigned short port, std::chrono::milliseconds timeout)
{
    using boost::asio::ip::tcp;
    boost::asio::io_context context;
    tcp::socket socket(context);
    boost::asio::steady_timer timer(context);
    std::array<unsigned char, 4> header {};
    const char request = 'C';
    std::string data;
    bool done = false;
    bool success = false;
    const auto finish = [&](bool ok) {
        if (done) return;
        done = true;
        success = ok;
        boost::system::error_code ignored;
        timer.cancel();
        socket.cancel(ignored);
        socket.close(ignored);
    };
    timer.expires_after(timeout);
    timer.async_wait([&](const boost::system::error_code& ec) { if (!ec) finish(false); });
    socket.async_connect(tcp::endpoint(boost::asio::ip::address_v4::loopback(), port),
        [&](const boost::system::error_code& ec) {
            if (done) return;
            if (ec) { finish(false); return; }
            boost::asio::async_write(socket, boost::asio::buffer(&request, 1),
                [&](const boost::system::error_code& write_ec, size_t) {
                    if (done) return;
                    if (write_ec) { finish(false); return; }
                    boost::asio::async_read(socket, boost::asio::buffer(header),
                        [&](const boost::system::error_code& header_ec, size_t) {
                            if (done) return;
                            if (header_ec) { finish(false); return; }
                            const uint32_t size = (uint32_t(header[0]) << 24) | (uint32_t(header[1]) << 16) |
                                                  (uint32_t(header[2]) << 8) | uint32_t(header[3]);
                            if (size < 4 || size > 32 * 1024 * 1024) { finish(false); return; }
                            data.resize(size);
                            boost::asio::async_read(socket, boost::asio::buffer(data),
                                [&](const boost::system::error_code& body_ec, size_t) {
                                    if (!done) finish(!body_ec);
                                });
                        });
                });
        });
    context.run();
    return success ? std::optional<std::string>(std::move(data)) : std::nullopt;
}
}
