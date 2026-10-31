#pragma once
#include <condition_variable>
#include <cstdint>
#include <mutex>

namespace asst
{
class TaskPauseGate
{
public:
    void pause()
    {
        std::lock_guard lock(m_mutex);
        if (!m_requested) {
            m_requested = true;
            ++m_epoch;
        }
    }

    void resume()
    {
        std::lock_guard lock(m_mutex);
        if (m_requested) {
            m_requested = false;
            ++m_epoch;
        }
        m_cv.notify_all();
    }

    void checkpoint() const
    {
        std::unique_lock lock(m_mutex);
        if (!m_requested || m_io_depth != 0) {
            return;
        }
        m_parked = true;
        m_cv.wait(lock, [&] { return !m_requested; });
        m_parked = false;
    }

    void begin_io()
    {
        std::lock_guard lock(m_mutex);
        ++m_io_depth;
    }

    void end_io()
    {
        std::lock_guard lock(m_mutex);
        if (m_io_depth > 0) {
            --m_io_depth;
        }
    }

    int state() const
    {
        std::lock_guard lock(m_mutex);
        return m_requested ? (m_parked ? 2 : 1) : 0;
    }

    uint64_t epoch() const
    {
        std::lock_guard lock(m_mutex);
        return m_epoch;
    }

private:
    mutable std::mutex m_mutex;
    mutable std::condition_variable m_cv;
    bool m_requested = false;
    mutable bool m_parked = false;
    uint64_t m_epoch = 0;
    int m_io_depth = 0;
};
}
