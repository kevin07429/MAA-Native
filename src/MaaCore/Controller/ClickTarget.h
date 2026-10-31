#pragma once

#include <algorithm>
#include <optional>

#include "Common/AsstTypes.h"

namespace asst
{
inline std::optional<Point> native_click_target(const Rect& rect, int width, int height)
{
    if (rect.empty() || width <= 0 || height <= 0) {
        return std::nullopt;
    }
    const Point center(rect.x + rect.width / 2, rect.y + rect.height / 2);
    if (center.x < 0 || center.x >= width || center.y < 0 || center.y >= height) {
        return std::nullopt;
    }
    // Legacy tasks sometimes specify a one-pixel point on the display boundary.
    // Keep those taps inside the application instead of the system gesture edge.
    const int margin = (std::min)({ 16, (width - 1) / 2, (height - 1) / 2 });
    return Point(std::clamp(center.x, margin, width - margin - 1), std::clamp(center.y, margin, height - margin - 1));
}
}
