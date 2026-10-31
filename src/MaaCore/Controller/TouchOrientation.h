#pragma once

#include <optional>
#include <string_view>

namespace asst
{
inline std::optional<int> parse_touch_orientation(std::string_view output)
{
    const auto read_digit = [&](size_t position) -> std::optional<int> {
        while (position < output.size() && (output[position] == ' ' || output[position] == '\t')) {
            ++position;
        }
        if (position < output.size() && output[position] >= '0' && output[position] <= '3') {
            return output[position] - '0';
        }
        return std::nullopt;
    };
    if (output.size() <= 4) {
        return read_digit(0);
    }
    constexpr std::string_view legacy = "SurfaceOrientation:";
    if (const auto position = output.find(legacy); position != std::string_view::npos) {
        return read_digit(position + legacy.size());
    }
    if (const auto viewport = output.find("Viewport INTERNAL:"); viewport != std::string_view::npos) {
        const auto rotation = output.find("orientation=", viewport);
        const auto end = output.find('\n', viewport);
        if (rotation != std::string_view::npos && (end == std::string_view::npos || rotation < end)) {
            return read_digit(rotation + std::string_view("orientation=").size());
        }
    }
    return std::nullopt;
}
}
