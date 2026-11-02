#pragma once

#include "AsstTypes.h"
#include <algorithm>
#include <cmath>
#include <string_view>

namespace asst::adaptive
{
inline Rect capture_canvas(int width, int height, int physical_width, int physical_height)
{
    if ((std::max)(width, height) == physical_width && (std::min)(width, height) == physical_height &&
        physical_height > WindowHeightDefault) {
        const double scale = static_cast<double>(WindowHeightDefault) / physical_height;
        return { 0, 0, static_cast<int>(std::lround(width * scale)), static_cast<int>(std::lround(height * scale)) };
    }
    return { 0, 0, width, height };
}

// Resource rectangles live in a 1280x720 canvas. Detected rectangles already
// live in the current canvas and MUST NOT pass through this conversion again.
inline Rect fixed_rect(Rect rect, int width, int height, std::string_view anchor = "auto")
{
    const int dx = width - WindowWidthDefault;
    const int dy = height - WindowHeightDefault;
    const int cx = rect.x + rect.width / 2;
    const int cy = rect.y + rect.height / 2;
    const auto offset = [](int center, int extent, int delta) {
        return center < extent / 4 ? 0 : (center > extent * 3 / 4 ? delta : delta / 2);
    };
    if (anchor == "absolute") {
        return rect;
    }
    rect.x += anchor == "left"     ? 0
              : anchor == "right"  ? dx
              : anchor == "center" ? dx / 2
                                   : offset(cx, WindowWidthDefault, dx);
    rect.y += offset(cy, WindowHeightDefault, dy);
    return rect;
}

// A Unity element may be left, center or right anchored. Expand resource ROIs
// to include all three candidates without stretching the template itself.
inline Rect search_rect(Rect rect, int width, int height)
{
    if (rect.empty()) {
        return rect;
    }
    rect.width += (std::max)(0, width - WindowWidthDefault);
    rect.height += (std::max)(0, height - WindowHeightDefault);
    return rect;
}
}
