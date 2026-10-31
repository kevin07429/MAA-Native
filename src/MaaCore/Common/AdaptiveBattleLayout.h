#pragma once

#include "Arknights-Tile-Pos/TileCalc2.hpp"
#include <algorithm>

namespace asst::adaptive
{
// Preserve vertical FOV on wide screens. Narrow screens use the game's
// camera adjustment between 16:9 and 4:3 instead of translating 16:9 tiles.
inline cv::Point project_battle(
    const Map::Level& level,
    const cv::Vec3d& world,
    bool side,
    int width,
    int height,
    const cv::Vec3d& offset = {})
{
    const double aspect = static_cast<double>(height) / width;
    const double adjustment = std::clamp((aspect - 9.0 / 16) / (3.0 / 4 - 9.0 / 16), 0.0, 1.0);
    const auto& view = level.view[side ? 1 : 0];
    const cv::Vec3d camera = cv::Vec3d(view.x - 1.4 * adjustment, view.y - 2.8 * adjustment, view.z) + offset;
    const auto matrix =
        Map::TileCalc2::camera_matrix_from_trans(camera, Map::TileCalc2::camera_euler_angles_yxz(level, side), aspect);
    auto result = matrix * cv::Point3d(world);
    result /= result(3);
    return { static_cast<int>(std::round((result(0) + 1) * width / 2)),
             static_cast<int>(std::round((1 - result(1)) * height / 2)) };
}
}
