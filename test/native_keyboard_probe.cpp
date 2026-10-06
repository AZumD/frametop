// Phase-0 probe for SteamVR's public native keyboard API.
//
// This intentionally does not touch Frametop's keyboard/input path. It connects as an
// OpenVR overlay client, asks SteamVR for its own keyboard, and prints the events Valve
// sends back. Run via test/_probe_native_keyboard.sh while SteamVR is already running.

#include <openvr.h>

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>

namespace {

constexpr uint64_t kUserValue = 0x46544b4250524f42ULL;  // "FTKBPROB"
std::atomic<bool> g_stop{false};

void Stop(int) { g_stop = true; }

std::string Escaped(const char *p, size_t n) {
    std::string out = "\"";
    char buf[8];
    for (size_t i = 0; i < n; ++i) {
        const unsigned char c = static_cast<unsigned char>(p[i]);
        switch (c) {
            case '\\': out += "\\\\"; break;
            case '"': out += "\\\""; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            case '\b': out += "\\b"; break;
            case 0x1b: out += "\\x1b"; break;
            default:
                if (c >= 0x20 && c != 0x7f) {
                    out.push_back(static_cast<char>(c));
                } else {
                    std::snprintf(buf, sizeof buf, "\\x%02x", c);
                    out += buf;
                }
        }
    }
    out += "\"";
    return out;
}

std::string Hex(const char *p, size_t n) {
    std::string out;
    char buf[4];
    for (size_t i = 0; i < n; ++i) {
        if (!out.empty()) out += ' ';
        std::snprintf(buf, sizeof buf, "%02x", static_cast<unsigned char>(p[i]));
        out += buf;
    }
    return out;
}

void PrintKeyboardEvent(const char *where, const vr::VREvent_t &ev) {
    const auto &k = ev.data.keyboard;
    if (k.uUserValue != kUserValue) return;

    if (ev.eventType == vr::VREvent_KeyboardCharInput) {
        const size_t n = strnlen(k.cNewInput, sizeof k.cNewInput);
        std::printf("%s char  utf8=%s  bytes=[%s]  overlay=%llu\n", where,
                    Escaped(k.cNewInput, n).c_str(), Hex(k.cNewInput, n).c_str(),
                    static_cast<unsigned long long>(k.overlayHandle));
    } else if (ev.eventType == vr::VREvent_KeyboardDone) {
        std::printf("%s DONE  overlay=%llu\n", where,
                    static_cast<unsigned long long>(k.overlayHandle));
    } else if (ev.eventType == vr::VREvent_KeyboardClosed ||
               ev.eventType == vr::VREvent_KeyboardClosed_Global) {
        std::printf("%s CLOSED  overlay=%llu\n", where,
                    static_cast<unsigned long long>(k.overlayHandle));
    } else if (ev.eventType == vr::VREvent_KeyboardOpened_Global) {
        std::printf("%s OPENED  overlay=%llu\n", where,
                    static_cast<unsigned long long>(k.overlayHandle));
    }
    std::fflush(stdout);
}

}  // namespace

int main(int argc, char **argv) {
    int seconds = 90;
    if (argc >= 2) {
        seconds = std::atoi(argv[1]);
        if (seconds < 5) seconds = 5;
        if (seconds > 600) seconds = 600;
    }

    std::signal(SIGINT, Stop);
    std::signal(SIGTERM, Stop);

    vr::EVRInitError init = vr::VRInitError_None;
    vr::VR_Init(&init, vr::VRApplication_Background);
    if (init != vr::VRInitError_None) {
        std::fprintf(stderr, "background init failed: %s\n",
                     vr::VR_GetVRInitErrorAsEnglishDescription(init));
        return 2;
    }
    vr::VR_Shutdown();

    init = vr::VRInitError_None;
    vr::VR_Init(&init, vr::VRApplication_Overlay);
    if (init != vr::VRInitError_None) {
        std::fprintf(stderr, "overlay init failed: %s\n",
                     vr::VR_GetVRInitErrorAsEnglishDescription(init));
        return 3;
    }

    auto *overlay = vr::VROverlay();
    auto *system = vr::VRSystem();
    if (!overlay || !system) {
        std::fprintf(stderr, "OpenVR interfaces unavailable\n");
        vr::VR_Shutdown();
        return 4;
    }

    vr::VROverlayHandle_t owner = vr::k_ulOverlayHandleInvalid;
    auto err = overlay->CreateOverlay("frametop.native-keyboard-probe",
                                      "Frametop native keyboard probe", &owner);
    if (err != vr::VROverlayError_None) {
        std::fprintf(stderr, "CreateOverlay failed: %s\n",
                     overlay->GetOverlayErrorNameFromEnum(err));
        vr::VR_Shutdown();
        return 5;
    }

    const uint32_t flags =
        vr::KeyboardFlag_Minimal |
        vr::KeyboardFlag_ShowArrowKeys |
        vr::KeyboardFlag_HideDoneKey;

    std::printf("requesting SteamVR keyboard for overlay %llu\n",
                static_cast<unsigned long long>(owner));
    err = overlay->ShowKeyboardForOverlay(
        owner,
        vr::k_EGamepadTextInputModeNormal,
        vr::k_EGamepadTextInputLineModeSingleLine,
        flags,
        "Frametop native keyboard probe",
        4096,
        "",
        kUserValue);

    if (err != vr::VROverlayError_None) {
        std::fprintf(stderr, "ShowKeyboardForOverlay failed: %s\n",
                     overlay->GetOverlayErrorNameFromEnum(err));
        std::fprintf(stderr, "trying ShowKeyboard without an owner overlay...\n");
        err = overlay->ShowKeyboard(
            vr::k_EGamepadTextInputModeNormal,
            vr::k_EGamepadTextInputLineModeSingleLine,
            flags,
            "Frametop native keyboard probe",
            4096,
            "",
            kUserValue);
    }

    if (err != vr::VROverlayError_None) {
        std::fprintf(stderr, "ShowKeyboard failed: %s\n",
                     overlay->GetOverlayErrorNameFromEnum(err));
        overlay->DestroyOverlay(owner);
        vr::VR_Shutdown();
        return 6;
    }

    std::printf(
        "keyboard request accepted.\n"
        "Type a few things with the Frame controllers, including if convenient:\n"
        "  hello 123, Backspace, Enter, arrows, and å ä ö\n"
        "Close the keyboard when done. Probe also exits after %d seconds.\n\n",
        seconds);
    std::fflush(stdout);

    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(seconds);
    bool closed = false;
    while (!g_stop && !closed && std::chrono::steady_clock::now() < deadline) {
        vr::VREvent_t ev{};

        // KeyboardCharInput and Done are documented as both global and overlay events.
        // Use the owner-overlay queue as the canonical character stream so each key is
        // printed once.
        while (overlay->PollNextOverlayEvent(owner, &ev, sizeof ev)) {
            if (ev.eventType == vr::VREvent_KeyboardCharInput ||
                ev.eventType == vr::VREvent_KeyboardDone ||
                ev.eventType == vr::VREvent_KeyboardClosed) {
                PrintKeyboardEvent("overlay", ev);
                if (ev.eventType == vr::VREvent_KeyboardClosed &&
                    ev.data.keyboard.uUserValue == kUserValue)
                    closed = true;
            }
        }

        while (system->PollNextEvent(&ev, sizeof ev)) {
            if (ev.eventType == vr::VREvent_KeyboardOpened_Global ||
                ev.eventType == vr::VREvent_KeyboardClosed_Global) {
                PrintKeyboardEvent("global ", ev);
                if (ev.eventType == vr::VREvent_KeyboardClosed_Global &&
                    ev.data.keyboard.uUserValue == kUserValue)
                    closed = true;
            }
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }

    char text[4096] = {};
    const uint32_t needed = overlay->GetKeyboardText(text, sizeof text);
    std::printf("\nGetKeyboardText: needed=%u text=%s\n", needed,
                Escaped(text, strnlen(text, sizeof text)).c_str());

    overlay->HideKeyboard();
    overlay->DestroyOverlay(owner);
    vr::VR_Shutdown();
    std::printf("probe finished\n");
    return 0;
}
