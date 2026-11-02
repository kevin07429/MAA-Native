#include "Common/AdaptiveBattleLayout.h"
#include "Common/AdaptiveLayout.h"
#include "Controller/ClickTarget.h"
#include "Controller/NativeCaptureSocket.h"
#include "Controller/TouchOrientation.h"
#include "Controller/adb-lite/protocol.hpp"
#include <boost/asio.hpp>
#include <chrono>
#include <future>
#include <iostream>
#include <stdexcept>
#include <thread>

using boost::asio::ip::tcp;

void require(bool value)
{
    if (!value) {
        throw std::runtime_error("regression test failed");
    }
}

int main()
{
    using asst::Rect;
    require(asst::parse_touch_orientation("1\n") == 1);
    require(asst::parse_touch_orientation("SurfaceOrientation: 3\n") == 3);
    require(
        asst::parse_touch_orientation(
            "touch.orientation.calibration: none\nViewport INTERNAL: displayId=0, orientation=1, "
            "logicalFrame=[0,0,2772,1280]\n") == 1);
    require(!asst::parse_touch_orientation("Viewport INTERNAL: displayId=0\norientation=2\n"));
    require(!asst::parse_touch_orientation(""));
    require(asst::native_click_target(Rect(1360, 656, 153, 43), 1559, 720) == asst::Point(1436, 677));
    require(asst::native_click_target(Rect(0, 719, 1, 1), 1559, 720) == asst::Point(16, 703));
    require(asst::native_click_target(Rect(2000, 100, 30, 30), 1559, 720) == std::nullopt);
    require(asst::native_click_target(Rect(20, 20, 0, 10), 1559, 720) == std::nullopt);
    using asst::adaptive::fixed_rect;
    using asst::adaptive::search_rect;
    require(asst::adaptive::capture_canvas(2772, 1280, 2772, 1280) == Rect(0, 0, 1559, 720));
    require(asst::adaptive::capture_canvas(1280, 2772, 2772, 1280) == Rect(0, 0, 720, 1559));
    require(asst::adaptive::capture_canvas(1559, 720, 2772, 1280) == Rect(0, 0, 1559, 720));
    require(asst::adaptive::capture_canvas(1920, 1080, 2772, 1280) == Rect(0, 0, 1920, 1080));
    require(asst::adaptive::capture_canvas(1280, 720, 1280, 720) == Rect(0, 0, 1280, 720));
    for (int width : { 1280, 1559, 1920 }) {
        require(fixed_rect(Rect(150, 620, 365, 35), width, 720, "left") == Rect(150, 620, 365, 35));
        require(fixed_rect(Rect(346, 626, 161, 52), width, 720, "left") == Rect(346, 626, 161, 52));
    }
    const Rect original { 100, 200, 40, 30 };
    require(fixed_rect(original, 1280, 720) == original);
    require(search_rect(original, 1280, 720) == original);
    require(search_rect(Rect {}, 1559, 720) == Rect {});
    require(search_rect(original, 1559, 720) == Rect(100, 200, 319, 30));
    require(fixed_rect(original, 1559, 720, "left") == original);
    require(fixed_rect(original, 1559, 720, "center") == Rect(239, 200, 40, 30));
    require(fixed_rect(original, 1559, 720, "right") == Rect(379, 200, 40, 30));
    require(fixed_rect(original, 1559, 720, "absolute") == original);
    require(fixed_rect(Rect(1100, 650, 40, 30), 1559, 720) == Rect(1379, 650, 40, 30));
    require(fixed_rect(Rect(600, 650, 40, 30), 1280, 800) == Rect(600, 730, 40, 30));

    Map::Level level;
    level.view = { { 0.3, -5.5, -8.3 }, { 0.6, -5.7, -8.1 } };
    for (bool side : { false, true }) {
        for (int x = -4; x <= 4; ++x) {
            for (int y = -3; y <= 3; ++y) {
                const cv::Vec3d world { static_cast<double>(x), static_cast<double>(y), -0.4 };
                const auto legacy = Map::TileCalc2::world_to_screen(level, world, side);
                require(asst::adaptive::project_battle(level, world, side, 1280, 720) == legacy);
                for (int width : { 1440, 1560, 1680, 2560 }) {
                    const auto wide = asst::adaptive::project_battle(level, world, side, width, 720);
                    require(wide == cv::Point(legacy.x + (width - 1280) / 2, legacy.y));
                }
                const auto narrow = asst::adaptive::project_battle(level, world, side, 1280, 960);
                const auto camera = Map::TileCalc2::camera_pos(level, side, 1280, 960);
                const auto matrix = Map::TileCalc2::camera_matrix_from_trans(
                    camera,
                    Map::TileCalc2::camera_euler_angles_yxz(level, side),
                    0.75);
                auto point = matrix * cv::Point3d(world);
                point /= point(3);
                require(
                    narrow == cv::Point(
                                  static_cast<int>(std::round((point(0) + 1) * 640)),
                                  static_cast<int>(std::round((1 - point(1)) * 480))));
            }
        }
    }
    for (const auto& [width, height] : { std::pair(1280, 720),
                                         std::pair(1280, 800),
                                         std::pair(1280, 960),
                                         std::pair(1560, 720),
                                         std::pair(2560, 720) }) {
        for (const auto& rect : { Rect(30, 30, 30, 30), Rect(600, 330, 80, 60), Rect(1200, 650, 60, 40) }) {
            const auto fixed = fixed_rect(rect, width, height);
            const auto search = search_rect(rect, width, height);
            require(fixed.x >= search.x && fixed.y >= search.y);
            require(fixed.x + fixed.width <= search.x + search.width);
            require(fixed.y + fixed.height <= search.y + search.height);
            require(asst::native_click_target(fixed, width, height).has_value());
        }
    }

    boost::asio::io_context context;
    tcp::acceptor acceptor(context, tcp::endpoint(boost::asio::ip::address_v4::loopback(), 0));
    std::string payload(3 * 1024 * 1024, '\0');
    for (size_t i = 0; i < payload.size(); ++i) {
        payload[i] = static_cast<char>(i % 251);
    }
    auto server = std::async(std::launch::async, [&] {
        tcp::socket peer(context);
        acceptor.accept(peer);
        std::array<char, 5> request {};
        boost::asio::read(peer, boost::asio::buffer(request));
        require(std::string(request.data(), 5) == "0001x");
        // Real TCP may split even a four-byte ADB header across packets.
        for (char ch : std::string("OKAY0005hello0004next")) {
            boost::asio::write(peer, boost::asio::buffer(&ch, 1));
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        boost::asio::write(peer, boost::asio::buffer(payload));
    });
    tcp::socket client(context);
    client.connect(acceptor.local_endpoint());
    adb::protocol::send_host_request(client, "x");
    require(adb::protocol::host_message(client) == "hello");
    require(adb::protocol::host_message(client) == "next");
    require(adb::protocol::host_data(client) == payload);
    server.get();
    auto frame_server = std::async(std::launch::async, [&] {
        tcp::socket peer(context);
        acceptor.accept(peer);
        char request = 0;
        boost::asio::read(peer, boost::asio::buffer(&request, 1));
        require(request == 'C');
        uint32_t length = static_cast<uint32_t>(payload.size());
        const std::array<unsigned char, 4> header { static_cast<unsigned char>(length >> 24),
                                                    static_cast<unsigned char>(length >> 16),
                                                    static_cast<unsigned char>(length >> 8),
                                                    static_cast<unsigned char>(length) };
        for (auto byte : header) {
            boost::asio::write(peer, boost::asio::buffer(&byte, 1));
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        boost::asio::write(peer, boost::asio::buffer(payload));
    });
    auto frame = asst::native_capture::read_frame(acceptor.local_endpoint().port(), std::chrono::milliseconds(1000));
    require(frame && *frame == payload);
    frame_server.get();
    auto stalled_server = std::async(std::launch::async, [&] {
        tcp::socket peer(context);
        acceptor.accept(peer);
        std::this_thread::sleep_for(std::chrono::milliseconds(80));
    });
    require(!asst::native_capture::read_frame(acceptor.local_endpoint().port(), std::chrono::milliseconds(20)));
    stalled_server.get();
    std::cout
        << "PASS: native anchors, 16:9 identity, expanded ROI, fragmented ADB headers, bounded messages, 3 MiB frame\n";
}
