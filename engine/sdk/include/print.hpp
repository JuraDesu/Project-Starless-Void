#pragma once

#include "content_api.h"

#include <ostream>
#include <streambuf>
#include <string>

class content_print_buffer final : public std::streambuf {
public:
    void bind(const EngineApi* api, void* engine_context) {
        api_ = api;
        engine_context_ = engine_context;
        emit_complete_lines();
    }

protected:
    int_type overflow(int_type value = traits_type::eof()) override {
        if (traits_type::eq_int_type(value, traits_type::eof())) {
            sync();
            return traits_type::not_eof(value);
        }
        append(static_cast<char>(value));
        return value;
    }

    std::streamsize xsputn(const char* data, std::streamsize count) override {
        if (!data || count <= 0) return 0;
        for (std::streamsize i = 0; i < count; ++i) append(data[i]);
        return count;
    }

    int sync() override {
        if (!api_) return 0;
        emit_complete_lines();
        if (!pending_.empty()) {
            emit_line(pending_);
            pending_.clear();
        }
        return 0;
    }

private:
    void append(char value) {
        if (value == '\n') {
            pending_.push_back(value);
            if (api_) emit_complete_lines();
        } else {
            pending_.push_back(value);
        }
    }

    void emit_complete_lines() {
        std::size_t start = 0;
        while (true) {
            const std::size_t end = pending_.find('\n', start);
            if (end == std::string::npos) {
                pending_.erase(0, start);
                return;
            }
            emit_line(pending_.substr(start, end - start));
            start = end + 1;
        }
    }

    void emit_line(const std::string& line) {
        if (!api_ || !api_->log) return;
        api_->log(engine_context_, 1u, line.c_str());
    }

    const EngineApi* api_{};
    void* engine_context_{};
    std::string pending_;
};

inline content_print_buffer content_print_buffer_instance;
inline std::ostream print{&content_print_buffer_instance};

inline void bind_content_print(
        const EngineApi* api, void* engine_context) {
    content_print_buffer_instance.bind(api, engine_context);
}
