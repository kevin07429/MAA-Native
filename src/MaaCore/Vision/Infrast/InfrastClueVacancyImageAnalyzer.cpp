#include "InfrastClueVacancyImageAnalyzer.h"

#include "MaaUtils/NoWarningCV.hpp"
#include "Utils/Logger.hpp"
#include "Vision/Matcher.h"
#include "Vision/RegionOCRer.h"

bool asst::InfrastClueVacancyImageAnalyzer::analyze()
{
    const static std::string clue_vacancy = "InfrastClueVacancy";

    Matcher analyzer(m_image);

    for (const std::string& suffix : m_to_be_analyzed) {
        analyzer.set_task_info(clue_vacancy + suffix);
        if (!analyzer.analyze()) {
            Log.trace("no", clue_vacancy, suffix);
            continue;
        }
        Rect rect = analyzer.get_result().rect;
        if (suffix.starts_with("No")) {
            // Wide search ROIs can include adjacent cards. Confirm the printed
            // slot number so a similar empty frame is not another clue number.
            RegionOCRer number_analyzer(m_image);
            number_analyzer.set_task_info("NumberOcrReplace");
            number_analyzer.set_roi(
                { rect.x + rect.width / 5, rect.y + rect.height / 6, rect.width * 3 / 5, rect.height / 2 });
            number_analyzer.set_use_char_model(true);
            const auto number = number_analyzer.analyze();
            if (!number || number->text != suffix.substr(2)) {
                LogInfo << __FUNCTION__ << "clue slot number does not match" << suffix;
                continue;
            }
        }
        Log.trace("has", clue_vacancy, suffix);
#ifdef ASST_DEBUG
        cv::rectangle(m_image_draw, make_rect<cv::Rect>(rect), cv::Scalar(0, 0, 255), 2);
        cv::putText(m_image_draw, suffix, cv::Point(rect.x, rect.y + 1), 0, 1, cv::Scalar(0, 0, 255), 2);
#endif
        m_clue_vacancy.emplace(suffix, rect);
    }

    return !m_clue_vacancy.empty();
}
