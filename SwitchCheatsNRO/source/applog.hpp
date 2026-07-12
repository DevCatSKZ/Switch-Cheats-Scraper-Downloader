#pragma once
// ---------------------------------------------------------------------------
// In-App-Protokoll (Seite "Protokoll"): thread-sicherer Ringpuffer.
// Worker-Threads und UI schreiben Zeilen; die Log-Seite rendert die letzten N.
// ---------------------------------------------------------------------------
#include <deque>
#include <mutex>
#include <string>
#include <vector>

namespace applog {

inline std::mutex& mtx() {
    static std::mutex m;
    return m;
}
inline std::deque<std::string>& buf() {
    static std::deque<std::string> b;
    return b;
}

inline void add(const std::string& line) {
    if (line.empty()) return;
    std::lock_guard<std::mutex> lk(mtx());
    auto& b = buf();
    b.push_back(line);
    while (b.size() > 400) b.pop_front();
}

// Kopie der letzten Zeilen (neueste zuletzt) fuer das Rendering.
inline std::vector<std::string> snapshot() {
    std::lock_guard<std::mutex> lk(mtx());
    return std::vector<std::string>(buf().begin(), buf().end());
}

inline size_t count() {
    std::lock_guard<std::mutex> lk(mtx());
    return buf().size();
}

} // namespace applog
