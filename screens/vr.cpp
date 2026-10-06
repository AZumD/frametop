// The OpenVR side of ft-screens: one overlay per screen, client DMA-BUFs imported with
// IVRIPCResourceManagerClient::ImportDmabuf (no copy, no size limit), panel mouse events
// turned into ft_events for the compositor, and the panels' own handling:
//   - a grab bar under each screen: press it with any laser (a controller, or the 3D
//     mouse's virtual controller) and the screen follows that device rigidly until the
//     release, so the 3D mouse's tilt (right button while dragging) turns it; scrolling
//     while dragging pushes it away or pulls it closer (along the line from the head).
//   - a curve button next to the bar: bends the screen into a cylinder around you (its
//     radius: your distance to it when pressed), or flat again.
//   - a roll button next to that: drag it sideways like a knob to roll the screen about
//     its centre (it snaps level within kRollSnap), or scroll on it for kRollStep steps.
//   - a resize tab on the bottom right corner: drag it to set the width (the height
//     follows the screen's resolution).
//   The controls are translucent, like SteamVR's own, and brighten under a laser. They
//   are invisible until a laser (a controller's, or the 3D mouse's) lands on or passes very close to
//   one of them (UpdateControls).
//   - pin to a wrist or the head: while carrying a screen, sweep the laser (the line from
//     the carrying device to the bar) across your other controller. A ring around each
//     controller shows the target and a dot where the laser passes it; crossing the ring
//     arms the pin (ring and bar turn blue), crossing it again disarms it. Let go while
//     armed and the screen rides on that controller as it is then. Grabbing a
//     controller-pinned screen keeps it armed for its wrist. Control-socket `pin` also
//     accepts "head" (HMD) via SetOverlayTransformTrackedDeviceRelative. A
//     controller-pinned screen shows only while you see its front, within the wrist
//     angle (fades over the last kFade degrees). Head-anchored screens follow the shared
//     visibility rules and stay put relative to the headset.
//   - visibility modes: always (the hide hotkey toggles), only with the SteamVR dashboard
//     open, hidden whenever the dashboard is open (except_dashboard), while you look at a
//     chosen controller (the wrist gesture), or toggle only (hidden until the hotkey shows
//     them).
//   - controllers on the screens: while visible, the screens can keep SteamVR's laser mouse
//     on (VROverlayFlags_MakeOverlaysInteractiveIfVisible), so controllers use them with
//     the dashboard closed. That also takes the controllers away from a VR or flatscreen
//     game, so by default it's off while AppActivity is not Desktop (outside_games): a
//     scene app, a visible desktopgame theater panel, or Steam's gamepad/diminished
//     presentation after "Enter gamepad mode". Modes: always, outside_games (default),
//     dashboard (only with the dashboard open).
//   - during a VR/flatscreen game the screens (and Spatial Instruments) hide unless the
//     dashboard is open (g_inGames, default), or stay visible over it; the hotkey still
//     shows them. See screens/app_activity.h.
//   - hand cutouts (handcut.cpp): where ft-hands (hands/) tracks a hand between an eye and a
//     screen, that eye sees through the screen (to Room View). Only then is the screen
//     drawn by us into a side-by-side buffer; otherwise its client buffer is shown as is.
//     Floating windows skip cutouts (texture-bounds crops). Tracking is opt-in (ft-handsctl).
//   - the catcher: a button pressed on a screen is released in KWin even when the laser
//     lets go between panels (UpdateCatcher). Needed for floating-window title-bar carry
//     and cross-panel releases.
//   - floating windows (docs/floating-windows.md): KWin's spare outputs, after the screens,
//     are panels too, for one window each. ft-floatd sizes the output to the window plus a
//     margin and tells us the window's rectangle ("float"): the panel shows only that crop of
//     the buffer. Dock/close buttons put it back on the desktop (both through ft-floatd).
// OpenVR has no overlay-relative transforms here (openvr v2.15.6), so the bar, button,
// and handle are placed whenever their screen moves.
#include "vr.h"
#include "app_activity.h"
#include "coords.h"
#include "handcut.h"
#include "keyboard.h"

#include <drm_fourcc.h>
#include <openvr.h>

#include <fcntl.h>
#include <linux/input-event-codes.h>
#include <limits.h>
#include <spawn.h>


#include <algorithm>
#include <chrono>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <ctime>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <csignal>
#include <dirent.h>
#include <fcntl.h>
#include <initializer_list>
#include <limits.h>
#include <map>
#include <string>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/un.h>
#include <unistd.h>
#include <vector>

#define STB_IMAGE_IMPLEMENTATION
#define STBI_ONLY_JPEG
#define STBI_ONLY_PNG
#define STBI_ONLY_GIF
#include "stb_image.h"

namespace {

using Mat = vr::HmdMatrix34_t;
using Clock = std::chrono::steady_clock;

Mat Identity() {
    Mat m{};
    m.m[0][0] = m.m[1][1] = m.m[2][2] = 1;
    return m;
}
Mat Mul(const Mat &a, const Mat &b) {
    Mat r{};
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 4; ++j) {
            double v = j == 3 ? a.m[i][3] : 0;
            for (int k = 0; k < 3; ++k) v += a.m[i][k] * b.m[k][j];
            r.m[i][j] = float(v);
        }
    }
    return r;
}
Mat Inverse(const Mat &a) {  // rigid: R^T, -R^T t
    Mat r{};
    for (int i = 0; i < 3; ++i)
        for (int j = 0; j < 3; ++j) r.m[i][j] = a.m[j][i];
    for (int i = 0; i < 3; ++i) r.m[i][3] = -(r.m[i][0] * a.m[0][3] + r.m[i][1] * a.m[1][3] + r.m[i][2] * a.m[2][3]);
    return r;
}
Mat Translation(double x, double y, double z) {
    Mat m = Identity();
    m.m[0][3] = float(x), m.m[1][3] = float(y), m.m[2][3] = float(z);
    return m;
}
double Dot3(const double a[3], const double b[3]) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
void Column(const Mat &m, int c, double out[3]) { out[0] = m.m[0][c], out[1] = m.m[1][c], out[2] = m.m[2][c]; }

// A panel pose from a centre and the direction its front is seen from (yaw, pitch; see
// layout: the front faces back along that direction), turned by roll.
Mat PanelPose(double x, double y, double z, double yawDeg, double pitchDeg, double rollDeg) {
    const double yw = yawDeg * M_PI / 180, pt = pitchDeg * M_PI / 180, rl = rollDeg * M_PI / 180;
    const double fx = -std::sin(yw) * std::cos(pt), fy = std::sin(pt), fz = -std::cos(yw) * std::cos(pt);
    const double Z[3] = {-fx, -fy, -fz};  // the front
    double X[3] = {Z[2], 0, -Z[0]};       // up x Z: horizontal right
    const double n = std::sqrt(X[0] * X[0] + X[2] * X[2]) + 1e-12;
    X[0] /= n, X[2] /= n;
    const double Y[3] = {Z[1] * X[2] - Z[2] * X[1], Z[2] * X[0] - Z[0] * X[2], Z[0] * X[1] - Z[1] * X[0]};
    const double c = std::cos(rl), s = std::sin(rl);
    Mat m{};
    for (int i = 0; i < 3; ++i) {
        m.m[i][0] = float(X[i] * c + Y[i] * s);
        m.m[i][1] = float(Y[i] * c - X[i] * s);
        m.m[i][2] = float(Z[i]);
    }
    m.m[0][3] = float(x), m.m[1][3] = float(y), m.m[2][3] = float(z);
    return m;
}

// Device poses, read once per tick (ft_vr_poll) or per command.
vr::TrackedDevicePose_t g_poses[vr::k_unMaxTrackedDeviceCount];
void RefreshPoses() {
    vr::VRSystem()->GetDeviceToAbsoluteTrackingPose(vr::TrackingUniverseStanding, 0, g_poses,
                                                    vr::k_unMaxTrackedDeviceCount);
}
bool DevicePose(vr::TrackedDeviceIndex_t dev, Mat *out) {
    if (dev >= vr::k_unMaxTrackedDeviceCount || !g_poses[dev].bPoseIsValid) return false;
    *out = g_poses[dev].mDeviceToAbsoluteTracking;
    return true;
}
// Where a device's laser starts and points: SteamVR's laser comes from its render model's
// "tip" component, not the device pose. On the Frame's controllers the tip points 40 degrees
// below the pose's -Z, so rays from the pose missed what the laser was on. Devices without
// a tip (the 3D mouse's virtual controller) aim along their pose. Cached per device; a
// model that isn't loaded yet is asked again a few seconds later.
struct Tip {
    std::string model;
    Mat offset = Identity();
    bool found = false;
    Clock::time_point checked;
};
Mat TipOffset(vr::TrackedDeviceIndex_t dev) {
    static std::map<vr::TrackedDeviceIndex_t, Tip> cache;
    char model[256] = "";
    vr::VRSystem()->GetStringTrackedDeviceProperty(dev, vr::Prop_RenderModelName_String, model, sizeof model);
    const auto now = Clock::now();
    auto it = cache.find(dev);
    if (it != cache.end() && it->second.model == model &&
        (it->second.found || now - it->second.checked < std::chrono::seconds(5)))
        return it->second.offset;
    Tip tip{model, Identity(), false, now};
    vr::RenderModel_ControllerMode_State_t mode{};
    vr::RenderModel_ComponentState_t state{};
    if (model[0] && vr::VRRenderModels()->GetComponentStateForDevicePath(model, vr::k_pch_Controller_Component_Tip,
                                                                          vr::k_ulInvalidInputValueHandle, &mode, &state))
        tip.offset = state.mTrackingToComponentLocal, tip.found = true;
    cache[dev] = tip;
    return tip.offset;
}
bool LaserPose(vr::TrackedDeviceIndex_t dev, Mat *out) {
    Mat d;
    if (!DevicePose(dev, &d)) return false;
    *out = Mul(d, TipOffset(dev));
    return true;
}

bool IsHandController(vr::TrackedDeviceIndex_t i) {
    if (vr::VRSystem()->GetTrackedDeviceClass(i) != vr::TrackedDeviceClass_Controller) return false;
    char type[64] = "";
    vr::VRSystem()->GetStringTrackedDeviceProperty(i, vr::Prop_ControllerType_String, type, sizeof type);
    return std::strcmp(type, "ft_pointer") != 0;  // not the 3D mouse's virtual controller
}
// Resolve a pin/anchor name to a tracked device: left/right controller roles, or the HMD.
vr::TrackedDeviceIndex_t AnchorDevice(const char *name) {
    if (std::strcmp(name, "head") == 0) return vr::k_unTrackedDeviceIndex_Hmd;
    if (std::strcmp(name, "right") == 0)
        return vr::VRSystem()->GetTrackedDeviceIndexForControllerRole(vr::TrackedControllerRole_RightHand);
    if (std::strcmp(name, "left") == 0)
        return vr::VRSystem()->GetTrackedDeviceIndexForControllerRole(vr::TrackedControllerRole_LeftHand);
    return vr::k_unTrackedDeviceIndexInvalid;
}
const char *AnchorName(vr::TrackedDeviceIndex_t i) {
    if (i == vr::k_unTrackedDeviceIndex_Hmd) return "head";
    switch (vr::VRSystem()->GetControllerRoleForTrackedDeviceIndex(i)) {
        case vr::TrackedControllerRole_LeftHand: return "left";
        case vr::TrackedControllerRole_RightHand: return "right";
        default: return "none";
    }
}
vr::TrackedDeviceIndex_t HandDevice(const char *hand) { return AnchorDevice(hand); }

enum class AnchorMode {
    World, Left, Right, HeadSoft, HeadRigid, YawFollow, PositionFollow
};
constexpr vr::TrackedDeviceIndex_t kNoneEarly = vr::k_unTrackedDeviceIndexInvalid;

bool IsSoftFollow(AnchorMode m) {
    return m == AnchorMode::HeadSoft || m == AnchorMode::YawFollow || m == AnchorMode::PositionFollow;
}
bool IsRigidDevice(AnchorMode m) {
    return m == AnchorMode::Left || m == AnchorMode::Right || m == AnchorMode::HeadRigid;
}
const char *AnchorModeName(AnchorMode m) {
    switch (m) {
        case AnchorMode::Left: return "left";
        case AnchorMode::Right: return "right";
        case AnchorMode::HeadSoft: return "head";
        case AnchorMode::HeadRigid: return "head-rigid";
        case AnchorMode::YawFollow: return "yaw-follow";
        case AnchorMode::PositionFollow: return "position-follow";
        default: return "world";
    }
}
AnchorMode ParseAnchorMode(const char *name) {
    if (!name) return AnchorMode::World;
    if (!std::strcmp(name, "left")) return AnchorMode::Left;
    if (!std::strcmp(name, "right")) return AnchorMode::Right;
    if (!std::strcmp(name, "head")) return AnchorMode::HeadSoft;  // legacy = soft
    if (!std::strcmp(name, "head-rigid")) return AnchorMode::HeadRigid;
    if (!std::strcmp(name, "yaw-follow")) return AnchorMode::YawFollow;
    if (!std::strcmp(name, "position-follow")) return AnchorMode::PositionFollow;
    if (!std::strcmp(name, "world") || !std::strcmp(name, "none")) return AnchorMode::World;
    return AnchorMode::World;
}
vr::TrackedDeviceIndex_t DeviceForMode(AnchorMode m) {
    switch (m) {
        case AnchorMode::Left: return AnchorDevice("left");
        case AnchorMode::Right: return AnchorDevice("right");
        case AnchorMode::HeadRigid: return vr::k_unTrackedDeviceIndex_Hmd;
        default: return kNoneEarly;
    }
}
AnchorMode CycleAnchor(AnchorMode m) {
    switch (m) {
        case AnchorMode::World: return AnchorMode::HeadSoft;
        case AnchorMode::HeadSoft: return AnchorMode::YawFollow;
        case AnchorMode::YawFollow: return AnchorMode::PositionFollow;
        default: return AnchorMode::World;
    }
}

// Upright reference: HMD position + yaw only (no pitch/roll).
Mat YawOnlyHead(const Mat &hmd) {
    const double yaw = std::atan2(hmd.m[0][2], hmd.m[2][2]);
    const double c = std::cos(yaw), s = std::sin(yaw);
    Mat m = Identity();
    m.m[0][0] = float(c), m.m[0][2] = float(s);
    m.m[2][0] = float(-s), m.m[2][2] = float(c);
    m.m[0][3] = hmd.m[0][3], m.m[1][3] = hmd.m[1][3], m.m[2][3] = hmd.m[2][3];
    return m;
}
Mat PositionOnlyHead(const Mat &hmd) {
    Mat m = Identity();
    m.m[0][3] = hmd.m[0][3], m.m[1][3] = hmd.m[1][3], m.m[2][3] = hmd.m[2][3];
    return m;
}
Mat ReferenceFrame(AnchorMode mode, const Mat &hmd) {
    switch (mode) {
        case AnchorMode::YawFollow: return YawOnlyHead(hmd);
        case AnchorMode::PositionFollow: return PositionOnlyHead(hmd);
        default: return hmd;  // HeadSoft / HeadRigid use full HMD; unused for world/controllers
    }
}

struct Quat { double w, x, y, z; };
Quat QuatFromMat(const Mat &m) {
    const double t = m.m[0][0] + m.m[1][1] + m.m[2][2];
    Quat q{};
    if (t > 0) {
        const double s = 0.5 / std::sqrt(t + 1.0);
        q.w = 0.25 / s;
        q.x = (m.m[2][1] - m.m[1][2]) * s;
        q.y = (m.m[0][2] - m.m[2][0]) * s;
        q.z = (m.m[1][0] - m.m[0][1]) * s;
    } else if (m.m[0][0] > m.m[1][1] && m.m[0][0] > m.m[2][2]) {
        const double s = 2.0 * std::sqrt(1.0 + m.m[0][0] - m.m[1][1] - m.m[2][2]);
        q.w = (m.m[2][1] - m.m[1][2]) / s;
        q.x = 0.25 * s;
        q.y = (m.m[0][1] + m.m[1][0]) / s;
        q.z = (m.m[0][2] + m.m[2][0]) / s;
    } else if (m.m[1][1] > m.m[2][2]) {
        const double s = 2.0 * std::sqrt(1.0 + m.m[1][1] - m.m[0][0] - m.m[2][2]);
        q.w = (m.m[0][2] - m.m[2][0]) / s;
        q.x = (m.m[0][1] + m.m[1][0]) / s;
        q.y = 0.25 * s;
        q.z = (m.m[1][2] + m.m[2][1]) / s;
    } else {
        const double s = 2.0 * std::sqrt(1.0 + m.m[2][2] - m.m[0][0] - m.m[1][1]);
        q.w = (m.m[1][0] - m.m[0][1]) / s;
        q.x = (m.m[0][2] + m.m[2][0]) / s;
        q.y = (m.m[1][2] + m.m[2][1]) / s;
        q.z = 0.25 * s;
    }
    return q;
}
Mat MatFromQuatPos(const Quat &q, double x, double y, double z) {
    const double xx = q.x * q.x, yy = q.y * q.y, zz = q.z * q.z;
    const double xy = q.x * q.y, xz = q.x * q.z, yz = q.y * q.z;
    const double wx = q.w * q.x, wy = q.w * q.y, wz = q.w * q.z;
    Mat m = Identity();
    m.m[0][0] = float(1 - 2 * (yy + zz));
    m.m[0][1] = float(2 * (xy - wz));
    m.m[0][2] = float(2 * (xz + wy));
    m.m[1][0] = float(2 * (xy + wz));
    m.m[1][1] = float(1 - 2 * (xx + zz));
    m.m[1][2] = float(2 * (yz - wx));
    m.m[2][0] = float(2 * (xz - wy));
    m.m[2][1] = float(2 * (yz + wx));
    m.m[2][2] = float(1 - 2 * (xx + yy));
    m.m[0][3] = float(x), m.m[1][3] = float(y), m.m[2][3] = float(z);
    return m;
}
Quat Slerp(Quat a, Quat b, double t) {
    double dot = a.w * b.w + a.x * b.x + a.y * b.y + a.z * b.z;
    if (dot < 0) { b.w = -b.w; b.x = -b.x; b.y = -b.y; b.z = -b.z; dot = -dot; }
    if (dot > 0.9995) {
        Quat r{a.w + t * (b.w - a.w), a.x + t * (b.x - a.x), a.y + t * (b.y - a.y), a.z + t * (b.z - a.z)};
        const double n = std::sqrt(r.w * r.w + r.x * r.x + r.y * r.y + r.z * r.z) + 1e-12;
        return {r.w / n, r.x / n, r.y / n, r.z / n};
    }
    const double th = std::acos(std::clamp(dot, -1.0, 1.0));
    const double s = std::sin(th), wa = std::sin((1 - t) * th) / s, wb = std::sin(t * th) / s;
    return {wa * a.w + wb * b.w, wa * a.x + wb * b.x, wa * a.y + wb * b.y, wa * a.z + wb * b.z};
}
void SmoothToward(Mat *cur, const Mat &target, double dt, double tauSec) {
    if (tauSec <= 1e-4 || dt <= 0) {
        *cur = target;
        return;
    }
    const double a = 1.0 - std::exp(-dt / tauSec);
    const Quat qa = QuatFromMat(*cur), qb = QuatFromMat(target);
    const Quat q = Slerp(qa, qb, a);
    *cur = MatFromQuatPos(q, cur->m[0][3] + a * (target.m[0][3] - cur->m[0][3]),
                          cur->m[1][3] + a * (target.m[1][3] - cur->m[1][3]),
                          cur->m[2][3] + a * (target.m[2][3] - cur->m[2][3]));
}

double QuatAngle(const Quat &a, const Quat &b) {
    double dot = a.w * b.w + a.x * b.x + a.y * b.y + a.z * b.z;
    if (dot < 0) dot = -dot;
    return 2.0 * std::acos(std::clamp(dot, 0.0, 1.0));
}

double WrapPi(double a) {
    return std::remainder(a, 2 * M_PI);
}

// Soft-follow dead zone: keep `lock` unless `cur` exceeds the zone, then push lock by the excess.
void PushFollowLock(Mat *lock, const Mat &cur, AnchorMode mode, double zoneDeg, double zoneM) {
    if (mode == AnchorMode::PositionFollow) {
        const double d[3] = {cur.m[0][3] - lock->m[0][3], cur.m[1][3] - lock->m[1][3],
                             cur.m[2][3] - lock->m[2][3]};
        const double len = std::sqrt(Dot3(d, d));
        if (len > zoneM && len > 1e-9) {
            const double f = (len - zoneM) / len;
            for (int k = 0; k < 3; ++k) lock->m[k][3] = float(lock->m[k][3] + d[k] * f);
        }
        return;
    }
    if (mode == AnchorMode::YawFollow) {
        const double ly = std::atan2(lock->m[0][2], lock->m[2][2]);
        const double cy = std::atan2(cur.m[0][2], cur.m[2][2]);
        const double dy = WrapPi(cy - ly);
        const double zone = zoneDeg * M_PI / 180.0;
        double yaw = ly;
        if (std::fabs(dy) > zone) yaw = ly + dy - std::copysign(zone, dy);
        // Keep walking with the head; only yaw is gated.
        *lock = YawOnlyHead(cur);
        const double c = std::cos(yaw), s = std::sin(yaw);
        lock->m[0][0] = float(c), lock->m[0][2] = float(s);
        lock->m[2][0] = float(-s), lock->m[2][2] = float(c);
        return;
    }
    // HeadSoft: gate full orientation; also allow a small position dead zone.
    const Quat qLock = QuatFromMat(*lock), qCur = QuatFromMat(cur);
    const double ang = QuatAngle(qLock, qCur);
    const double zone = zoneDeg * M_PI / 180.0;
    Quat q = qLock;
    if (ang > zone && ang > 1e-8) q = Slerp(qLock, qCur, (ang - zone) / ang);
    double pos[3] = {lock->m[0][3], lock->m[1][3], lock->m[2][3]};
    const double d[3] = {cur.m[0][3] - pos[0], cur.m[1][3] - pos[1], cur.m[2][3] - pos[2]};
    const double len = std::sqrt(Dot3(d, d));
    if (len > zoneM && len > 1e-9) {
        const double f = (len - zoneM) / len;
        for (int k = 0; k < 3; ++k) pos[k] += d[k] * f;
    }
    *lock = MatFromQuatPos(q, pos[0], pos[1], pos[2]);
}

std::string LayoutToolPath() {
    char exe[PATH_MAX] = {};
    const ssize_t n = readlink("/proc/self/exe", exe, sizeof exe - 1);
    if (n <= 0) return {};
    exe[n] = 0;
    std::string path(exe);
    // .../screens/build/ft-screens -> .../layout/ft-layout
    const auto cut = path.rfind("/screens/");
    if (cut == std::string::npos) return {};
    return path.substr(0, cut) + "/layout/ft-layout";
}

void SpawnLayoutAsync(std::initializer_list<const char *> args) {
    const std::string bin = LayoutToolPath();
    if (bin.empty()) {
        std::fprintf(stderr, "ft-screens: cannot find ft-layout beside this binary\n");
        return;
    }
    signal(SIGCHLD, SIG_IGN);  // avoid zombies from fire-and-forget applies
    pid_t pid = fork();
    if (pid < 0) return;
    if (pid == 0) {
        // Detach from the compositor process group; never block the VR poll loop.
        setsid();
        int fd = open("/dev/null", O_RDWR);
        if (fd >= 0) { dup2(fd, 0); dup2(fd, 1); dup2(fd, 2); if (fd > 2) close(fd); }
        std::vector<char *> argv;
        argv.push_back(const_cast<char *>(bin.c_str()));
        for (const char *a : args) argv.push_back(const_cast<char *>(a));
        argv.push_back(nullptr);
        execv(bin.c_str(), argv.data());
        _exit(127);
    }
}

enum class Drag { None, Move, Resize, Roll };
enum class Mode { Always, Dashboard, ExceptDashboard, Gesture, Toggle };
enum class Lasers { Always, OutsideGames, Dashboard };
enum class InGames { Visible, Hide };

enum class GazeKind {
    None, Screen, Bar, Curve, Roll, Resize, Anchor, Slot, Instrument, Dock, Toolbar
};

struct GazeTarget {
    GazeKind kind = GazeKind::None;
    int screen = -1;       // 0-based index into g_screens
    int instrument = -1;   // 0-based index into g_instruments
    int slot = -1;         // 0-based profile slot when kind == Slot
    double u = 0, v = 0;   // normalized on screen surface (0..1 top-left)
    double localX = 0, localY = 0;
    double distance = 1e9;
    explicit operator bool() const { return kind != GazeKind::None; }
};

constexpr double kWristZone = 0.06;  // the laser passing this close to a controller is on its wrist
constexpr double kWristLeave = 0.09; // ...and has left it beyond this (so it doesn't flicker)
constexpr double kDotRange = 0.35;   // the guide dot shows while the laser is this close
constexpr double kMinWidth = 0.15;
constexpr double kFade = 10;         // degrees over which a pinned screen fades out
constexpr double kRollSnap = 2.5;    // degrees from level where rolling snaps level
constexpr double kRollStep = 5;      // degrees per scroll notch on the roll button
constexpr float kChromeIdle = 0.55f; // the controls' opacity without a laser on them
constexpr float kChromeFloor = 0.4f; // chrome stays at least this visible when screen alpha is 0
constexpr long kControlsLinger = 35; // ticks (~0.4 s) the controls stay after a laser leaves
long g_tick = 0;                     // ft_vr_poll calls
bool g_vr = false;                   // connected to SteamVR (ft-screens --no-vr runs without it)
constexpr vr::TrackedDeviceIndex_t kNone = kNoneEarly;
constexpr int kSlotCount = 6;
double g_followLagMs = 120;
int g_currentSlot = 0;
bool g_slotFilled[kSlotCount] = {};
Clock::time_point g_lastFollow = Clock::now();

// --- eye gaze (OpenVR IVRInput eyetracking action) ---
vr::VRActionSetHandle_t g_actionSet = vr::k_ulInvalidActionSetHandle;
vr::VRActionHandle_t g_eyeAction = vr::k_ulInvalidActionHandle;
bool g_eyeManifestOk = false;     // action manifest loaded
bool g_eyeAvailable = false;      // hardware/runtime has delivered valid data at least once
bool g_eyeValid = false;          // current sample is usable
bool g_eyeHeld = false;           // reusing last good ray through a brief dropout
int g_eyeLastErr = 0;             // last EVRInputError from GetEyeTrackingData*
int g_eyeFlags = 0;               // bit0=active bit1=valid bit2=tracked (last sample)
bool g_gazeDebug = false;
bool g_gazeFallbackHead = false;  // explicit debug fallback only — never silent
double g_gazeOrigin[3] = {}, g_gazeDir[3] = {0, 0, -1};
double g_lastEyeOrigin[3] = {}, g_lastEyeDir[3] = {0, 0, -1};
GazeTarget g_gazeTarget;
Clock::time_point g_lastGaze = Clock::now();
Clock::time_point g_lastEyeValid{};
constexpr double kEyeSampleHoldSec = 0.45;  // keep last ray when OpenVR eye samples flicker




// Shared SteamVR-inspired chrome grammar (used by screen chrome + toolbar grab bar).
namespace ChromeStyle {
constexpr float kIdle = 0.60f;
constexpr float kFloor = 0.4f;
constexpr int kBarTexW = 256;
constexpr int kBarTexH = 24;
constexpr int kControlTexN = 64;
constexpr double kGapFrac = 0.06;
constexpr double kBarHalfHFrac = 12.0 / 256.0;
constexpr double kBarVisualHFrac = 0.55;
constexpr uint8_t kIdleR = 0x3d, kIdleG = 0x44, kIdleB = 0x50;
constexpr uint8_t kActiveR = 255, kActiveG = 255, kActiveB = 255;
constexpr uint8_t kBarIdleA = 200, kBarLitA = 245;
}  // namespace ChromeStyle

#include "spatial.inc"

// A popup or dialog of a floating window: a small panel over it, cut from the same buffer.
struct Sub {
    vr::VROverlayHandle_t overlay = vr::k_ulOverlayHandleInvalid;
    int x = 0, y = 0, w = 0, h = 0;  // in the output's buffer, pixels
};

struct Screen : FollowState, AttentionState, MoveDrag {
    vr::VROverlayHandle_t overlay = vr::k_ulOverlayHandleInvalid, bar = vr::k_ulOverlayHandleInvalid,
                          handle = vr::k_ulOverlayHandleInvalid, curveButton = vr::k_ulOverlayHandleInvalid,
                          rollButton = vr::k_ulOverlayHandleInvalid,
                          anchorButton = vr::k_ulOverlayHandleInvalid,
                          dockButton = vr::k_ulOverlayHandleInvalid,
                          closeButton = vr::k_ulOverlayHandleInvalid;  // float dock/close; also toolbar dock
    int width = 0, height = 0;    // DMA-BUF / OpenVR mouse scale (buffer pixels)
    int surfaceWidth = 0, surfaceHeight = 0;  // Wayland surface-local logical size
    double outputScale = 1.0;     // KWin output scale (Display Settings); for pointer seat map
    double metres = 1;
    double curve = 0;             // cylinder radius in metres; 0 = flat
    const void *shown = nullptr;  // a frame arrived
    bool visible = false;         // shown in VR right now
    const void *key = nullptr;    // the client buffer on it now, and its dmabuf (for cutouts)
    ft_dmabuf buf{};
    vr::SharedTextureHandle_t plain = 0;  // that buffer's SteamVR import
    bool cutting = false;         // showing a cutout buffer (side by side) instead
    bool alone = false;           // concealed: kept off the headset (windows stay on the screen)
    float visibilityFade = 1.f;
    double grabX = 0, grabY = 0;              // resize: the grab point relative to the corner
    Mat rollFrom = Identity();                // roll: the pose at the press (pinRel when pinned)
    double rollAngle = 0;                     // the laser's angle around the centre then
    bool hover[4] = {};                       // bar, curve, roll, resize
    bool hoverAnchor = false;
    bool hoverDock = false, hoverClose = false;
    // Docked to the spatial toolbar (toolbar → dock anchor → screen).
    bool docked = false;
    int dockSlot = 0;
    FollowState preDock;
    // Dock/undock fly: same cosine ease + ~450 ms as ft-layout profile apply.
    bool dockTween = false;
    bool dockTweenUndock = false;             // flying back to preDock (not riding the bar)
    Clock::time_point dockTweenStart{};
    Mat dockTweenFrom = Identity();
    Mat dockTweenTo = Identity();             // undock end pose (world)
    FollowState dockTweenRestore;             // FollowState applied when undock tween ends
    bool gazeHover = false;                   // any gaze hit on this screen or its chrome
    bool lasers = true;                       // MakeOverlaysInteractiveIfVisible is set
    float controls = 0;                       // the controls' fade, 0 (hidden) .. 1
    bool controlsUp = false;                  // the controls' overlays are shown
    long nearUntil = 0;                       // a laser was near the controls until this tick
    vr::TrackedDeviceIndex_t pinTarget = kNone;  // moving: rides on this device when let go
    vr::TrackedDeviceIndex_t onWrist = kNone;    // moving: the laser is in this controller's ring
    bool barLit = false;
    double chrome = 0.3;          // the bar's width; the other controls follow it (ChromeSize)
    double grip = 0.04;           // the corner tab's and the round buttons' size
    // A floating window's panel: the window's rectangle in the buffer, its title bar height,
    // and the density (metres per buffer pixel).
    bool floating = false;        // a spare output's panel
    int floatSlot = 0;            // 1-based; overlay key frametop.float.N
    bool floatOn = false;         // ft-floatd has a window on it ("float" .. "unfloat")
    bool outputOn = false;        // KWin has the spare output turned on
    bool minimized = false;
    int cropX = 0, cropY = 0, cropW = 0, cropH = 0;
    int titleH = 0;
    double mpp = 0;               // metres per buffer pixel
    bool titleCarry = false;      // carried by its title bar: KWin's pointer stays at carryX, carryY
    double carryX = 0, carryY = 0;
    long resizeSent = 0;          // g_tick of the last resize request (they're throttled)
    int resizeW = 0, resizeH = 0; // ...and its size
    std::map<int, Sub> subs;
    double heightMetres() const {
        if (floating && cropW > 0) return metres * cropH / cropW;
        return width > 0 ? metres * height / width : metres * 9 / 16;
    }
    float ComposedAlpha() const { return attentionResolved * visibilityFade; }
    // chrome stays discoverable when the screen surface is fully transparent
    float ChromeAlpha() const {
        return std::max(ComposedAlpha(), controls > 0.02f ? kChromeFloor : 0.f);
    }
    std::vector<vr::VROverlayHandle_t> Controls() const {
        // Profiles live in the toolbar's Displays popup, not under every screen.
        std::vector<vr::VROverlayHandle_t> out = {bar, curveButton, rollButton, handle, anchorButton, dockButton};
        if (floating) out.push_back(closeButton);
        return out;
    }
    std::vector<vr::VROverlayHandle_t> All() const {
        auto out = Controls();
        out.insert(out.begin(), overlay);
        return out;
    }
};
std::map<int, Screen> g_screens;
std::map<const void *, vr::SharedTextureHandle_t> g_imports;

bool ScreenDocked(const Screen &s) { return s.docked; }

// desktop_toolbar.inc (included near the end of this namespace).
bool ToolbarWanted();
void EndToolbarDragsBy(vr::TrackedDeviceIndex_t dev);
void ToggleScreenDock(int index);
bool StartToolbarDrag(vr::TrackedDeviceIndex_t dev);
void PickToolbarGaze(const Mat &ray, const double origin[3], GazeTarget *best);

// Hand cutouts (optional; inert until ft-hands publishes /run/user/UID/frametop-hands/hands).
bool g_cutouts = true;          // the cutouts command turns them off
handcut::Hands g_hands;
handcut::Renderer g_cutter;
int g_cutterState = 0;          // 0 not tried, 1 ready, -1 unavailable
std::map<const void *, vr::SharedTextureHandle_t> g_cutImports;

// --- Spatial Instruments (ambient VR info; not desktop surfaces) ---
enum class InstrumentType { Clock, Battery, Storage, Sd, Date, Media, Image, Launcher };

struct ImageFrame {
    std::vector<uint8_t> rgba;
    int delayMs = 100;
};

struct Instrument : FollowState, AttentionState, MoveDrag {
    Instrument() {
        idleOpacity = 0.35f;
        attentionEnabled = true;
    }
    std::string id;
    InstrumentType type = InstrumentType::Clock;
    bool enabled = false;
    vr::VROverlayHandle_t overlay = vr::k_ulOverlayHandleInvalid;
    vr::VROverlayHandle_t bar = vr::k_ulOverlayHandleInvalid;
    double metres = 0.35;
    bool hoverBar = false;
    bool barLit = false;
    float controls = 0;
    bool controlsUp = false;
    long nearUntil = 0;
    bool gazeHover = false;
    bool visible = false;
    float visibilityFade = 1.f;  // shared ModeVisible / wrist fade (same as screens)
    int lastMinute = -1;       // Clock content key (hour*60+min)
    int lastBatterySeg = -1;   // Battery filled-segment count last drawn
    int lastStorageKey = -1;   // Storage/Sd: present*1000 + used_pct (0–100)
    int lastDateKey = -1;      // Date: year*512 + yday
    int lastMediaKey = -1;     // Media: hash of status+text+caps (not scroll)
    int lastMediaScrollPx = -1;  // last uploaded marquee pixel offset
    std::string mediaText;     // marquee label from MPRIS
    int mediaStatus = 0;       // 0 none, 1 stopped, 2 paused, 3 playing
    bool mediaCanPrev = false, mediaCanPause = false, mediaCanNext = false;
    double mediaScroll = 0;    // marquee pixel offset
    double mediaScrollAcc = 0; // sub-pixel accumulator for slow marquee
    std::string imagePath;
    std::vector<ImageFrame> imageFrames;
    int imageFrame = 0;
    double imageFrameAccMs = 0;
    int lastImageFrame = -1;
    // Launcher: action + appearance (independent). Gaze never activates.
    std::string launchKind;       // application | action | command | shell
    std::string launchTarget;     // desktop id, semantic name, or shell text / unused for command
    std::string launchCommandJson;  // JSON argv array when launchKind == command
    std::string launchAppear;     // app | glyph | image | fallback
    std::string launchGlyph;      // play, star, …
    int lastLauncherKey = -1;
    uint8_t colorR = 57, colorG = 255, colorB = 20;  // CRT green default (#39FF14)
    int texW = 384, texH = 128;
    std::vector<uint8_t> pixels;
    double heightMetres() const { return metres * double(texH) / double(texW); }
    float ComposedAlpha() const { return attentionResolved * visibilityFade; }
};

std::vector<Instrument> g_instruments;

// Headset battery via sysfs (Steam Frame: max1720x fuel-gauge Battery node).
std::string g_batteryCapacityPath;
int g_batteryPct = -1;  // last valid 0–100; -1 = never read
Clock::time_point g_batteryNextPoll{};
Clock::time_point g_batteryNextDiscover{};
int g_batteryFailLogBudget = 3;

// Device + SD storage pools (unique block mounts summed; SD may be unmounted).
struct StoragePool {
    bool present = false;
    bool mounted = false;
    uint64_t total = 0;
    uint64_t used = 0;
    int pct = 0;  // 0–100
};
StoragePool g_storageDevice, g_storageSd;
Clock::time_point g_storageNextPoll{};
int g_storageFailLogBudget = 3;

bool InstrumentPose(const Instrument &inst, Mat *out);
void UpdateInstrumentAttention(double dt);
void UpdateInstrumentVisibility();
void TickInstruments(double dt);
void EndInstrumentDragsBy(vr::TrackedDeviceIndex_t dev);
void ClearInstruments();


// Visibility (see the top). g_manual is the hide/show switch: in the always mode it hides
// the screens, in the others it shows them anyway.
Mode g_mode = Mode::Always;
bool g_manual = false;
double g_wristAngle = 60;    // a pinned screen shows while you see its front within this
double g_gestureAngle = 20;  // gesture: look within this of the controller
std::string g_gestureHand = "left";
Lasers g_lasers = Lasers::OutsideGames;  // when controllers' lasers work the screens (see the top)
frametop::AppActivity g_appActivity = frametop::AppActivity::Desktop;
frametop::AppActivityState g_appActivityState{};
std::map<vr::VROverlayHandle_t, std::string> g_desktopgameOverlays;
bool g_gameRunning = false;  // AppHidesDisplays(g_appActivity): hide displays / Always→Dashboard
InGames g_inGames = InGames::Hide;  // during a game, the always mode acts like the dashboard mode

// ---------------------------------------------------------------- chrome (bar, button, handle)

// The controls look like SteamVR's own: a light translucent pill for the bar, dark
// translucent discs with white glyphs for the buttons (the overlay alpha, kChromeIdle,
// dims them further until a laser is on them).
std::vector<uint8_t> PillTexture(int w, int h, uint8_t red, uint8_t green, uint8_t blue, uint8_t alpha,
                                 double visualHFrac = 1.0) {
    std::vector<uint8_t> px(size_t(w) * h * 4, 0);
    const double visH = std::max(2.0, h * std::clamp(visualHFrac, 0.2, 1.0));
    const double r = visH / 2.0 - 1;
    const double cy = h / 2.0;
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x) {
            const double cx = std::clamp(double(x), r + 1, w - r - 1);
            const double d = std::hypot(x + 0.5 - cx, y + 0.5 - cy);
            uint8_t *p = &px[(size_t(y) * w + x) * 4];
            p[0] = red, p[1] = green, p[2] = blue;
            p[3] = uint8_t(std::clamp(r - d + 0.5, 0.0, 1.0) * alpha);
        }
    return px;
}
const std::vector<uint8_t> &BarTexture(bool lit) {
    static const auto normal = PillTexture(256, 24, 235, 235, 235, 210), glow = PillTexture(256, 24, 90, 170, 255, 240);
    return lit ? glow : normal;
}

// Paint a control: dark translucent inside `inside(u, v)`, white where `glyph(u, v)`, a
// faint light rim where `rim(u, v)`. u, v: -1..1 across the texture, v up.
template <typename In, typename Glyph, typename Rim>
std::vector<uint8_t> ControlTexture(int n, In inside, Glyph glyph, Rim rim) {
    std::vector<uint8_t> px(size_t(n) * n * 4, 0);
    const int ss = 3;  // supersampling, for smooth edges
    for (int y = 0; y < n; ++y)
        for (int x = 0; x < n; ++x) {
            double in = 0, g = 0, e = 0;
            for (int j = 0; j < ss; ++j)
                for (int i = 0; i < ss; ++i) {
                    const double u = (x + (i + 0.5) / ss) / n * 2 - 1, v = 1 - (y + (j + 0.5) / ss) / n * 2;
                    if (!inside(u, v)) continue;
                    in += 1;
                    if (glyph(u, v)) g += 1;
                    else if (rim(u, v)) e += 1;
                }
            const double k = ss * ss;
            in /= k, g /= k, e /= k;
            uint8_t *p = &px[(size_t(y) * n + x) * 4];
            const double bg = in - g - e;  // dark part
            const double a = bg * 0.72 + e * 0.6 + g * 1.0;
            if (a <= 0) continue;
            const double shade = (bg * 0.72 * 38 + e * 0.6 * 200 + g * 255) / a;
            p[0] = p[1] = p[2] = uint8_t(std::clamp(shade, 0.0, 255.0));
            p[3] = uint8_t(std::clamp(a * 255, 0.0, 255.0));
        }
    return px;
}
bool InDisc(double u, double v) { return u * u + v * v <= 1; }
bool DiscRim(double u, double v) { return u * u + v * v > 0.86 * 0.86; }

std::vector<uint8_t> CloseTexture(int n) {
    // A cross: "close this window".
    return ControlTexture(
        n, InDisc,
        [](double u, double v) {
            return std::max(std::fabs(u), std::fabs(v)) < 0.42 &&
                   (std::fabs(u - v) < 0.12 || std::fabs(u + v) < 0.12);
        },
        DiscRim);
}

// Dock / Undock glyphs (SteamVR Minimize / Popout outlines as polygons).
struct SvgPt {
    double x, y;
};
constexpr SvgPt kDockBar[] = {{4, 27}, {32, 27}, {32, 32}, {4, 32}};
constexpr SvgPt kDockChevron[] = {{29, 10.77}, {25.48, 7.23}, {18, 14.72}, {10.5, 7.23}, {7, 10.77}, {18, 21.77}};
constexpr SvgPt kUndockArrow[] = {{32, 4},     {32, 16},   {28, 16}, {28, 10.83}, {19, 19.83},
                                  {16.19, 17}, {25.19, 8}, {20, 8},  {20, 4}};
constexpr SvgPt kUndockBox[] = {{28, 28}, {8, 28}, {8, 8},   {13, 8},  {13, 4},
                                {4, 4},   {4, 32}, {32, 32}, {32, 23}, {28, 23}};

template <size_t N>
bool InSvgPolygon(const SvgPt (&poly)[N], double x, double y) {
    bool in = false;
    for (size_t i = 0, j = N - 1; i < N; j = i++)
        if ((poly[i].y > y) != (poly[j].y > y) &&
            x < (poly[j].x - poly[i].x) * (y - poly[i].y) / (poly[j].y - poly[i].y) + poly[i].x)
            in = !in;
    return in;
}

// docked: the Undock (float in world) glyph; otherwise Dock (return to the toolbar / desktop).
std::vector<uint8_t> DockTexture(int n, bool docked = false) {
    constexpr double kIconHalf = 0.62;
    return ControlTexture(
        n, InDisc,
        [docked](double u, double v) {
            const double x = (u / kIconHalf + 1) * 18, y = (1 - v / kIconHalf) * 18;
            if (docked) return InSvgPolygon(kUndockArrow, x, y) || InSvgPolygon(kUndockBox, x, y);
            return InSvgPolygon(kDockBar, x, y) || InSvgPolygon(kDockChevron, x, y);
        },
        DiscRim);
}

std::vector<uint8_t> CornerTexture(int n) {
    // A quarter disc whose corner (the texture's top left) sits on the screen's bottom
    // right corner, with two grip arcs: "drag this corner".
    auto r = [](double u, double v) { return std::hypot(u + 1, v - 1) / 2; };  // 0..1 from the corner
    return ControlTexture(
        n, [&](double u, double v) { return r(u, v) <= 1; },
        [&](double u, double v) {
            const double d = r(u, v);
            return std::fabs(d - 0.5) < 0.035 || std::fabs(d - 0.75) < 0.035;
        },
        [&](double u, double v) { return r(u, v) > 0.93; });
}

std::vector<uint8_t> CurveTexture(int n) {
    // An arc: "curve this screen".
    return ControlTexture(
        n, InDisc,
        [](double u, double v) { return std::fabs(std::hypot(u, -v - 1.9) - 1.7) < 0.11 && std::fabs(u) < 0.6; },
        DiscRim);
}

std::vector<uint8_t> RollTexture(int n) {
    // A circular arrow, counterclockwise: "roll this screen".
    return ControlTexture(
        n, InDisc,
        [](double u, double v) {
            const double r = std::hypot(u, v);
            double ang = std::atan2(v, u) * 180 / M_PI;
            if (ang < 0) ang += 360;
            if (std::fabs(r - 0.48) < 0.085 && ang >= 100) return true;  // the arc, 100..360 degrees
            // The head at 0 degrees, pointing up (the way the arc turns there).
            const double hx = u - 0.48, hy = v + 0.02;
            return hy >= 0 && hy <= 0.3 && std::fabs(hx) <= 0.24 * (1 - hy / 0.3);
        },
        DiscRim);
}

std::vector<uint8_t> DigitTexture(int n, int digit, bool lit) {
    // Simple seven-segment-ish digit in a disc; lit = current slot.
    auto on = [digit](int seg) {
        // segments: 0 top, 1 UL, 2 UR, 3 mid, 4 LL, 5 LR, 6 bot
        static const int bits[10] = {0x77, 0x24, 0x5D, 0x6D, 0x2E, 0x6B, 0x7B, 0x25, 0x7F, 0x6F};
        return (bits[digit % 10] >> seg) & 1;
    };
    return ControlTexture(
        n, InDisc,
        [&](double u, double v) {
            const double t = 0.12;
            if (on(0) && v > 0.45 && v < 0.45 + t && std::fabs(u) < 0.35) return true;
            if (on(6) && v < -0.45 && v > -0.45 - t && std::fabs(u) < 0.35) return true;
            if (on(3) && std::fabs(v) < t / 2 && std::fabs(u) < 0.35) return true;
            if (on(1) && u < -0.25 && u > -0.25 - t && v > 0 && v < 0.45) return true;
            if (on(2) && u > 0.25 && u < 0.25 + t && v > 0 && v < 0.45) return true;
            if (on(4) && u < -0.25 && u > -0.25 - t && v < 0 && v > -0.45) return true;
            if (on(5) && u > 0.25 && u < 0.25 + t && v < 0 && v > -0.45) return true;
            return false;
        },
        lit ? [](double u, double v) { return u * u + v * v > 0.7 * 0.7; } : DiscRim);
}

std::vector<uint8_t> AnchorTexture(int n, AnchorMode mode) {
    // Glyph hints: W / H / Y / P
    const char ch = mode == AnchorMode::HeadSoft || mode == AnchorMode::HeadRigid ? 'H'
                  : mode == AnchorMode::YawFollow                                 ? 'Y'
                  : mode == AnchorMode::PositionFollow                            ? 'P'
                                                                                  : 'W';
    return ControlTexture(
        n, InDisc,
        [ch](double u, double v) {
            // crude letter strokes in the disc
            if (ch == 'W')
                return (std::fabs(u + 0.35) < 0.08 && v > -0.4 && v < 0.4) ||
                       (std::fabs(u - 0.35) < 0.08 && v > -0.4 && v < 0.4) ||
                       (std::fabs(u) < 0.08 && v > -0.4 && v < 0.05) ||
                       (std::fabs(v + 0.35 - std::fabs(u) * 0.4) < 0.08 && std::fabs(u) < 0.35);
            if (ch == 'H')
                return (std::fabs(u + 0.28) < 0.09 && std::fabs(v) < 0.4) ||
                       (std::fabs(u - 0.28) < 0.09 && std::fabs(v) < 0.4) || (std::fabs(v) < 0.08 && std::fabs(u) < 0.28);
            if (ch == 'Y')
                return (std::fabs(v - std::fabs(u) * 0.9) < 0.09 && v > 0 && std::fabs(u) < 0.35) ||
                       (std::fabs(u) < 0.09 && v < 0.1 && v > -0.4);
            // P
            return (std::fabs(u + 0.25) < 0.09 && std::fabs(v) < 0.4) ||
                   (v > 0.05 && std::fabs(std::hypot(u - 0.05, v - 0.2) - 0.22) < 0.09 && u > -0.1);
        },
        DiscRim);
}

vr::VROverlayHandle_t CreateOrRecycleOverlay(const char *key, const char *name) {
    vr::VROverlayHandle_t o = vr::k_ulOverlayHandleInvalid;
    if (vr::VROverlay()->CreateOverlay(key, name, &o) == vr::VROverlayError_None) return o;
    // Key left behind after a hard kill (no VR_Shutdown): reclaim and retry.
    if (vr::VROverlay()->FindOverlay(key, &o) == vr::VROverlayError_None) {
        vr::VROverlay()->DestroyOverlay(o);
        o = vr::k_ulOverlayHandleInvalid;
        if (vr::VROverlay()->CreateOverlay(key, name, &o) == vr::VROverlayError_None) return o;
    }
    return vr::k_ulOverlayHandleInvalid;
}

vr::VROverlayHandle_t MakeChrome(const char *key, const char *name, const std::vector<uint8_t> &px, int w, int h) {
    vr::VROverlayHandle_t o = CreateOrRecycleOverlay(key, name);
    if (o == vr::k_ulOverlayHandleInvalid) return o;
    vr::VROverlay()->SetOverlayRaw(o, const_cast<uint8_t *>(px.data()), uint32_t(w), uint32_t(h), 4);
    vr::VROverlay()->SetOverlayInputMethod(o, vr::VROverlayInputMethod_Mouse);
    // SteamVR hit-tests by the mouse-scale aspect, not the texture's: at the default 1x1
    // a 10:1 bar catches the laser across a width x width square of invisible space.
    // Re-uploads at another size must set it again (see UploadToolbarBacking).
    const vr::HmdVector2_t scale = {{float(w), float(h)}};
    vr::VROverlay()->SetOverlayMouseScale(o, &scale);
    // Keep chrome just above its panel (sort 1). Sort 10 sat above SteamVR's own UI
    // regardless of distance — Frametop must not win the foreground that way.
    vr::VROverlay()->SetOverlaySortOrder(o, 1);
    return o;
}

void LightBar(Screen &s, bool lit) {
    if (s.barLit == lit) return;
    s.barLit = lit;
    const auto &px = BarTexture(lit);
    vr::VROverlay()->SetOverlayRaw(s.bar, const_cast<uint8_t *>(px.data()), 256, 24, 4);
}

// ---------------------------------------------------------------- wrist guides

// While a screen is carried, each other controller gets a ring (its wrist zone, facing
// you) and a dot where the laser passes closest to it. Blue: armed / in the ring.
std::vector<uint8_t> DiscTexture(int n, double stroke, uint8_t red, uint8_t green, uint8_t blue, uint8_t fill,
                                 uint8_t rimShade) {
    std::vector<uint8_t> px(size_t(n) * n * 4, 0);
    const double c = n / 2.0, r = n / 2.0 - 1;
    for (int y = 0; y < n; ++y)
        for (int x = 0; x < n; ++x) {
            const double d = std::hypot(x + 0.5 - c, y + 0.5 - c);
            const double a = std::clamp(r - d + 0.5, 0.0, 1.0);
            uint8_t *p = &px[(size_t(y) * n + x) * 4];
            const bool rim = d > r - stroke;
            const bool edge = d > r - 2 || (rim && d < r - stroke + 2);  // a dark line each side of the rim
            p[0] = edge ? rimShade : red, p[1] = edge ? rimShade : green, p[2] = edge ? rimShade : blue;
            p[3] = uint8_t(a * (rim ? 235 : fill));
        }
    return px;
}
const std::vector<uint8_t> &RingTexture(bool lit) {
    static const auto normal = DiscTexture(128, 9, 240, 240, 240, 40, 60),
                      glow = DiscTexture(128, 12, 90, 170, 255, 110, 30);
    return lit ? glow : normal;
}
const std::vector<uint8_t> &DotTexture(bool lit) {
    static const auto normal = DiscTexture(32, 16, 250, 250, 250, 250, 50),
                      glow = DiscTexture(32, 16, 90, 170, 255, 250, 30);
    return lit ? glow : normal;
}

struct GuidePart {
    vr::VROverlayHandle_t overlay = vr::k_ulOverlayHandleInvalid;
    int lit = -1;  // the texture on it (-1: none yet)
    bool shown = false;
    void Show(bool on) {
        if (on == shown || overlay == vr::k_ulOverlayHandleInvalid) return;
        shown = on;
        if (on) vr::VROverlay()->ShowOverlay(overlay);
        else vr::VROverlay()->HideOverlay(overlay);
    }
    void Light(bool on, const std::vector<uint8_t> &px, int n) {
        if (int(on) == lit) return;
        lit = on;
        vr::VROverlay()->SetOverlayRaw(overlay, const_cast<uint8_t *>(px.data()), uint32_t(n), uint32_t(n), 4);
    }
};
struct Guide { GuidePart ring, dot; };
std::map<vr::TrackedDeviceIndex_t, Guide> g_guides;

Guide &GuideFor(vr::TrackedDeviceIndex_t dev) {
    auto it = g_guides.find(dev);
    if (it != g_guides.end()) return it->second;
    Guide &g = g_guides[dev];
    char key[64];
    std::snprintf(key, sizeof key, "frametop.guide.%u.ring", dev);
    if (vr::VROverlay()->CreateOverlay(key, "Wrist pin target", &g.ring.overlay) == vr::VROverlayError_None) {
        vr::VROverlay()->SetOverlayWidthInMeters(g.ring.overlay, float(2 * kWristZone));
        vr::VROverlay()->SetOverlaySortOrder(g.ring.overlay, 20);
    }
    std::snprintf(key, sizeof key, "frametop.guide.%u.dot", dev);
    if (vr::VROverlay()->CreateOverlay(key, "Wrist pin laser", &g.dot.overlay) == vr::VROverlayError_None) {
        vr::VROverlay()->SetOverlayWidthInMeters(g.dot.overlay, 0.022f);
        vr::VROverlay()->SetOverlaySortOrder(g.dot.overlay, 21);
    }
    return g;
}

// A pose at pt facing the head (upright).
Mat FacingPose(const double pt[3], const Mat &head) {
    double z[3] = {head.m[0][3] - pt[0], head.m[1][3] - pt[1], head.m[2][3] - pt[2]};
    const double zl = std::sqrt(Dot3(z, z)) + 1e-9;
    for (double &v : z) v /= zl;
    double x[3] = {z[2], 0, -z[0]};  // up x z
    const double xl = std::sqrt(x[0] * x[0] + x[2] * x[2]);
    if (xl < 1e-6) x[0] = 1, x[2] = 0;
    else x[0] /= xl, x[2] /= xl;
    const double y[3] = {z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]};
    Mat m{};
    for (int i = 0; i < 3; ++i) m.m[i][0] = float(x[i]), m.m[i][1] = float(y[i]), m.m[i][2] = float(z[i]), m.m[i][3] = float(pt[i]);
    return m;
}

void ApplyCurve(const Screen &s) {
    // OpenVR's curvature: the fraction of a full cylinder the overlay's width covers.
    const double c = s.curve > 0 ? std::clamp(s.metres / (2 * M_PI * s.curve), 0.0, 1.0) : 0.0;
    vr::VROverlay()->SetOverlayCurvature(s.overlay, float(c));
}

// The screen's pose in the room (a pinned one: its anchor device's pose times pinRel).
bool ScreenPose(const Screen &s, Mat *out) {
    if (s.pinned != kNone) {
        Mat d;
        if (!DevicePose(s.pinned, &d)) return false;
        *out = Mul(d, s.pinRel);
        return true;
    }
    // Our own copy: reading it back from SteamVR right after setting it could return the
    // old pose, which left a moved screen's controls behind.
    *out = s.pose;
    return true;
}

// The controls' size from both the screen's width and its distance from the head (the
// geometric mean of 12% of the width and 10% of the distance), so a small screen near you
// gets small controls and a big or far one gets big ones, never under about 1.7 degrees.
void ChromeSize(Screen &s) {
    Mat head, p;
    double dist = 2;
    if (DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head) && ScreenPose(s, &p)) {
        const double d[3] = {p.m[0][3] - head.m[0][3], p.m[1][3] - head.m[1][3], p.m[2][3] - head.m[2][3]};
        dist = std::max(0.2, std::sqrt(Dot3(d, d)));
    }
    const double least = dist * 0.03;
    s.chrome = std::clamp(std::sqrt(0.012 * dist * s.metres), least, std::max(least, s.metres * 0.5));
    s.grip = std::max(s.chrome * 0.13, dist * 0.018);
}

// A point on the screen's surface, u metres along it from the centre (along the arc when
// curved), v up, dz out of it, facing the way the surface does there. OpenVR curves a
// screen into a cylinder toward its front, with its centre line where the flat one was.
Mat OnSurface(const Screen &s, double u, double v, double dz) {
    if (s.curve <= 0) return Translation(u, v, dz);
    const double r = s.curve, a = u / r, c = std::cos(a), sn = std::sin(a);
    Mat m = Identity();
    m.m[0][0] = float(c), m.m[0][2] = float(-sn);
    m.m[2][0] = float(sn), m.m[2][2] = float(c);
    m.m[0][3] = float(r * sn - dz * sn), m.m[1][3] = float(v), m.m[2][3] = float(r - r * c + dz * c);
    return m;
}

double BarY(const Screen &s) { return -(s.heightMetres() / 2 + s.chrome * 0.06 + s.chrome * 12 / 256); }
Mat BarOffset(const Screen &s) { return OnSurface(s, 0, BarY(s), 0.003); }

// Dock / Undock: right of the roll button (same button grammar as curve/roll).
double DockButtonX(const Screen &s) {
    const double gap = s.chrome * 0.06;
    return s.chrome / 2 + gap * 3 + s.grip * 2.5;
}

// Bottom strip: bar / curve / roll / resize / anchor / dock [/ close for floats].
std::vector<Mat> ControlOffsets(const Screen &s) {
    const double h = s.heightMetres(), bar = s.chrome, button = s.grip, gap = bar * 0.06;
    std::vector<Mat> out;
    out.push_back(BarOffset(s));
    out.push_back(OnSurface(s, bar / 2 + gap + button / 2, BarY(s), 0.003));
    out.push_back(OnSurface(s, bar / 2 + gap * 2 + button * 1.5, BarY(s), 0.003));
    out.push_back(OnSurface(s, s.metres / 2 + s.grip / 2, -(h / 2 + s.grip / 2), 0.003));
    out.push_back(OnSurface(s, -(bar / 2 + gap + button / 2), BarY(s), 0.003));
    out.push_back(OnSurface(s, DockButtonX(s), BarY(s), 0.003));
    if (s.floating) {
        // Close further right of the dock button.
        out.push_back(OnSurface(s, DockButtonX(s) + gap + button, BarY(s), 0.003));
    }
    return out;
}

// A floating window's popups and dialogs, a few millimetres in front of it, where they are
// in the buffer relative to the window.
void PlaceSubs(const Screen &s) {
    if (s.subs.empty() || s.cropW <= 0) return;
    Mat p;
    if (s.pinned == kNone && !ScreenPose(s, &p)) return;
    for (const auto &[k, sub] : s.subs) {
        const double u = (sub.x + sub.w / 2.0 - (s.cropX + s.cropW / 2.0)) * s.mpp;
        const double v = -(sub.y + sub.h / 2.0 - (s.cropY + s.cropH / 2.0)) * s.mpp;
        const Mat off = OnSurface(s, u, v, 0.005);
        vr::VROverlay()->SetOverlayWidthInMeters(sub.overlay, float(std::max(0.01, sub.w * s.mpp)));
        if (s.pinned != kNone) {
            const Mat m = Mul(s.pinRel, off);
            vr::VROverlay()->SetOverlayTransformTrackedDeviceRelative(sub.overlay, s.pinned, &m);
        } else {
            const Mat m = Mul(p, off);
            vr::VROverlay()->SetOverlayTransformAbsolute(sub.overlay, vr::TrackingUniverseStanding, &m);
        }
    }
}

void PlaceChrome(Screen &s) {
    ChromeSize(s);
    const double bar = s.chrome, button = s.grip;
    const auto offsets = ControlOffsets(s);
    auto setW = [](vr::VROverlayHandle_t o, float w) {
        if (o != vr::k_ulOverlayHandleInvalid) vr::VROverlay()->SetOverlayWidthInMeters(o, w);
    };
    setW(s.bar, float(bar));
    setW(s.curveButton, float(button));
    setW(s.rollButton, float(button));
    setW(s.handle, float(s.grip));
    setW(s.anchorButton, float(button));
    // Always size the dock (non-float used to skip this → default/huge overlay).
    setW(s.dockButton, float(button));
    if (s.floating) setW(s.closeButton, float(button));
    if (s.bar != vr::k_ulOverlayHandleInvalid)
        vr::VROverlay()->SetOverlayCurvature(s.bar, s.curve > 0 ? float(std::min(1.0, bar / (2 * M_PI * s.curve))) : 0.f);
    PlaceSubs(s);
    auto controls = s.Controls();
    if (s.pinned != kNone) {
        for (size_t i = 0; i < controls.size() && i < offsets.size(); ++i) {
            if (controls[i] == vr::k_ulOverlayHandleInvalid) continue;
            const Mat m = Mul(s.pinRel, offsets[i]);
            vr::VROverlay()->SetOverlayTransformTrackedDeviceRelative(controls[i], s.pinned, &m);
        }
        return;
    }
    Mat p;
    if (!ScreenPose(s, &p)) return;
    for (size_t i = 0; i < controls.size() && i < offsets.size(); ++i) {
        if (controls[i] == vr::k_ulOverlayHandleInvalid) continue;
        const Mat m = Mul(p, offsets[i]);
        vr::VROverlay()->SetOverlayTransformAbsolute(controls[i], vr::TrackingUniverseStanding, &m);
    }
}

void ApplyScreenTransform(Screen &s) {
    Mat p;
    if (!ScreenPose(s, &p)) return;
    if (s.pinned != kNone)
        vr::VROverlay()->SetOverlayTransformTrackedDeviceRelative(s.overlay, s.pinned, &s.pinRel);
    else
        vr::VROverlay()->SetOverlayTransformAbsolute(s.overlay, vr::TrackingUniverseStanding, &p);
    PlaceChrome(s);
}

void SetAbsolute(Screen &s, const Mat &pose) {
    SetWorldPose(s, pose);
    ApplyScreenTransform(s);
}

void SetFollow(Screen &s, AnchorMode mode, const Mat &rel) {
    // Capture what's on screen *before* changing mode so soft follow can seed from it
    // (avoids a pop when a profile pins after a world-space transition).
    Mat seed;
    const bool haveSeed = ScreenPose(s, &seed);

    s.anchor = mode;
    s.pinRel = rel;
    if (IsRigidDevice(mode)) {
        const vr::TrackedDeviceIndex_t dev = DeviceForMode(mode);
        Mat c;
        if (dev == kNone || !DevicePose(dev, &c)) return;
        s.pinned = dev;
        vr::VROverlay()->SetOverlayTransformTrackedDeviceRelative(s.overlay, dev, &s.pinRel);
        PlaceChrome(s);
        return;
    }
    s.pinned = kNone;
    if (haveSeed) {
        s.pose = seed;
    } else {
        Mat hmd;
        if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &hmd)) hmd = Identity();
        s.pose = Mul(ReferenceFrame(mode, hmd), rel);
    }
    // Seed dead-zone lock to the current reference so a fresh pin doesn't jump.
    {
        Mat hmd;
        if (DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &hmd)) {
            s.followLock = ReferenceFrame(mode, hmd);
            s.followLockValid = true;
        } else {
            s.followLockValid = false;
        }
    }
    vr::VROverlay()->SetOverlayTransformAbsolute(s.overlay, vr::TrackingUniverseStanding, &s.pose);
    PlaceChrome(s);
}

void Pin(Screen &s, vr::TrackedDeviceIndex_t dev, const Mat &rel) {
    // Wrist / legacy path: map device to mode.
    AnchorMode mode = AnchorMode::World;
    if (dev == vr::k_unTrackedDeviceIndex_Hmd) mode = AnchorMode::HeadRigid;
    else if (!std::strcmp(AnchorName(dev), "left")) mode = AnchorMode::Left;
    else if (!std::strcmp(AnchorName(dev), "right")) mode = AnchorMode::Right;
    else return;
    SetFollow(s, mode, rel);
}

void EndDrag(Screen &s);  // defined with drag handling below

void RefreshSlotTextures(Screen &s) {
    // Name kept: toolbar Displays popup still tracks g_slotFilled; screen chrome no longer
    // has digit slot overlays. Refresh dock/anchor glyphs only.
    if (s.dockButton != vr::k_ulOverlayHandleInvalid) {
        auto px = DockTexture(64, s.docked);
        vr::VROverlay()->SetOverlayRaw(s.dockButton, px.data(), 64, 64, 4);
        const vr::HmdVector2_t scale = {{64.f, 64.f}};
        vr::VROverlay()->SetOverlayMouseScale(s.dockButton, &scale);
    }
    if (s.anchorButton != vr::k_ulOverlayHandleInvalid) {
        auto px = AnchorTexture(64, s.anchor);
        vr::VROverlay()->SetOverlayRaw(s.anchorButton, px.data(), 64, 64, 4);
        const vr::HmdVector2_t scale = {{64.f, 64.f}};
        vr::VROverlay()->SetOverlayMouseScale(s.anchorButton, &scale);
    }
}

void CycleScreenAnchor(Screen &s) {
    Mat world;
    if (!ScreenPose(s, &world)) return;
    EndDrag(s);
    const AnchorMode next = CycleAnchor(s.anchor);
    if (next == AnchorMode::World) {
        SetAbsolute(s, world);
    } else {
        Mat hmd;
        if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &hmd)) return;
        SetFollow(s, next, Mul(Inverse(ReferenceFrame(next, hmd)), world));
    }
    RefreshSlotTextures(s);
    std::printf("screen: anchor %s\n", AnchorModeName(s.anchor));
}

void UpdateFollow() {
    const auto now = Clock::now();
    const double dt = std::chrono::duration<double>(now - g_lastFollow).count();
    g_lastFollow = now;
    if (dt <= 0 || dt > 0.25) return;  // skip huge stalls
    Mat hmd;
    if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &hmd)) return;
    const double tau = g_followLagMs / 1000.0;
    for (auto &[i, s] : g_screens) {
        if (s.drag != Drag::None || !IsSoftFollow(s.anchor)) continue;
        // Head-soft only: freeze while gaze-focused so reading does not pitch/slide the
        // surface under your eyes. Yaw-follow and position-follow are meant to keep
        // moving while you look at them — freezing those felt like path stutter when
        // eye samples flickered on/off the panel.
        if (s.attentionEnabled && s.attentionFocused && s.anchor == AnchorMode::HeadSoft) {
            if (s.followDeadzone) {
                const Mat cur = ReferenceFrame(s.anchor, hmd);
                s.followLock = cur;
                s.followLockValid = true;
            }
            continue;
        }
        const Mat cur = ReferenceFrame(s.anchor, hmd);
        Mat ref = cur;
        // Position-follow always gets a tiny dead zone so millimetre HMD noise does not
        // jitter a still sitter. User deadzone (if any) is at least this large.
        const double posFloorM = 0.025;  // 2.5 cm
        const bool useDeadzone =
            s.followDeadzone || s.anchor == AnchorMode::PositionFollow;
        if (useDeadzone) {
            if (!s.followLockValid) {
                s.followLock = cur;
                s.followLockValid = true;
            }
            const double zoneDeg = s.followDeadzone ? s.followDeadzoneDeg : 15.0;
            const double zoneM = s.followDeadzone ? std::max(s.followDeadzoneM, posFloorM)
                                                 : posFloorM;
            PushFollowLock(&s.followLock, cur, s.anchor, zoneDeg, zoneM);
            ref = s.followLock;
        } else {
            s.followLockValid = false;
        }
        const Mat target = Mul(ref, s.pinRel);
        SmoothToward(&s.pose, target, dt, tau);
        vr::VROverlay()->SetOverlayTransformAbsolute(s.overlay, vr::TrackingUniverseStanding, &s.pose);
        PlaceChrome(s);
    }
}

// Screens you walk up to (or pinned ones you bring close) get their controls resized now
// and then, not every frame.
void RefreshChrome() {
    static int tick = 0;
    if (++tick % 45) return;
    for (auto &[i, s] : g_screens) {
        if (s.drag != Drag::None) continue;
        const double before = s.chrome;
        ChromeSize(s);
        if (std::fabs(s.chrome - before) > before * 0.08) PlaceChrome(s);
        else s.chrome = before;
    }
}

void SetWidth(Screen &s, double metres) {
    s.metres = std::clamp(metres, kMinWidth, 12.0);
    vr::VROverlay()->SetOverlayWidthInMeters(s.overlay, float(s.metres));
    ApplyCurve(s);  // same radius, so the curvature fraction changes with the width
    PlaceChrome(s);
}

// Curve toward the head: the radius is the head's distance to the screen now.
void ToggleCurve(Screen &s) {
    Mat head, p;
    if (s.curve > 0 || !DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head) || !ScreenPose(s, &p)) {
        s.curve = 0;
    } else {
        const double dx = p.m[0][3] - head.m[0][3], dy = p.m[1][3] - head.m[1][3], dz = p.m[2][3] - head.m[2][3];
        s.curve = std::max(0.5, std::sqrt(dx * dx + dy * dy + dz * dz));
    }
    ApplyCurve(s);
    PlaceChrome(s);
}

// ---------------------------------------------------------------- visibility

// Angle in degrees between a panel's front and the direction from it to the head.
double FacingAngle(const Mat &p, const Mat &head) {
    double n[3], to[3] = {head.m[0][3] - p.m[0][3], head.m[1][3] - p.m[1][3], head.m[2][3] - p.m[2][3]};
    Column(p, 2, n);
    const double len = std::sqrt(Dot3(to, to)) + 1e-9;
    return std::acos(std::clamp(Dot3(n, to) / len, -1.0, 1.0)) * 180 / M_PI;
}

// The screens' shared visibility for the mode (before a pinned screen's own facing rule).
// During a SteamVR/flat game, In games = hide owns visibility regardless of the normal
// desktop mode: yield to the game while its dashboard is closed, show with the dashboard,
// and still allow the manual hotkey override through Mode::Dashboard.
Mode EffectiveMode() {
    return g_gameRunning && g_inGames == InGames::Hide ? Mode::Dashboard : g_mode;
}

// Flatscreen / gamescope theater panels (not scene apps). Steam uses both legacy
// slot-like keys and app-id keys such as valve.steam.desktopgame.1145360. OpenVR cannot
// enumerate another app's overlays, so keep handles learned from OverlayCreated events
// and seed them once at startup with vrcmd for the "Frametop restarted mid-game" case.
void RememberDesktopgameOverlay(vr::VROverlayHandle_t handle) {
    if (handle == vr::k_ulOverlayHandleInvalid) return;
    char key[vr::k_unVROverlayMaxKeyLength] = {};
    vr::EVROverlayError err = vr::VROverlayError_None;
    vr::VROverlay()->GetOverlayKey(handle, key, sizeof key, &err);
    if (err != vr::VROverlayError_None || !frametop::IsDesktopgameOverlayKey(key)) return;
    if (g_desktopgameOverlays.emplace(handle, key).second) {
        std::printf("desktopgame discovered %s\n", key);
        std::fflush(stdout);
    }
}

void ForgetDesktopgameOverlay(vr::VROverlayHandle_t handle) {
    g_desktopgameOverlays.erase(handle);
}

void SeedDesktopgameOverlays() {
    // Cheap compatibility fallback for the historical keys.
    auto find = [](const char *key) {
        vr::VROverlayHandle_t handle = vr::k_ulOverlayHandleInvalid;
        if (vr::VROverlay()->FindOverlay(key, &handle) == vr::VROverlayError_None)
            RememberDesktopgameOverlay(handle);
    };
    find("valve.steam.desktopgame");
    for (int i = 0; i < 16; ++i) {
        char key[64];
        std::snprintf(key, sizeof key, "valve.steam.desktopgame.%d", i);
        find(key);
    }

    FILE *p = popen(
        "LD_LIBRARY_PATH=/opt/steamvr/bin/linuxarm64 "
        "/opt/steamvr/bin/linuxarm64/vrcmd --overlays 2>/dev/null",
        "r");
    if (!p) return;
    char line[1024];
    while (std::fgets(line, sizeof line, p)) {
        if (line[0] != '\'') continue;
        const char *end = std::strchr(line + 1, '\'');
        if (!end) continue;
        const std::string key(line + 1, size_t(end - (line + 1)));
        if (!frametop::IsDesktopgameOverlayKey(key.c_str())) continue;
        find(key.c_str());
    }
    pclose(p);
}

void FlatscreenDesktopgame(bool *registered, bool *visible) {
    *registered = false;
    *visible = false;
    for (auto it = g_desktopgameOverlays.begin(); it != g_desktopgameOverlays.end();) {
        char key[vr::k_unVROverlayMaxKeyLength] = {};
        vr::EVROverlayError err = vr::VROverlayError_None;
        vr::VROverlay()->GetOverlayKey(it->first, key, sizeof key, &err);
        if (err != vr::VROverlayError_None || !frametop::IsDesktopgameOverlayKey(key)) {
            it = g_desktopgameOverlays.erase(it);
            continue;
        }
        it->second = key;
        *registered = true;
        if (vr::VROverlay()->IsOverlayVisible(it->first)) {
            *visible = true;
            return;
        }
        ++it;
    }
}

// Scene apps, visible desktopgame theater, and Steam's gamepad presentation (dashboard
// hidden while a latched desktopgame key remains) share one AppActivity. Checked ~2 Hz.
void UpdateGame() {
    if (g_tick % 45) return;
    const bool scene = vr::VRApplications()->GetCurrentSceneProcessId() != 0;
    bool flatReg = false, flatVis = false;
    FlatscreenDesktopgame(&flatReg, &flatVis);
    const bool dash = vr::VROverlay()->IsDashboardVisible();
    const auto prev = g_appActivity;
    const bool prevLatch = g_appActivityState.flatLatch;
    g_appActivity = frametop::DecideAppActivity(scene, flatVis, flatReg, dash, &g_appActivityState);
    const bool running = frametop::AppHidesDisplays(g_appActivity);
    if (g_appActivity == prev && running == g_gameRunning &&
        prevLatch == g_appActivityState.flatLatch)
        return;
    if (running != g_gameRunning) g_manual = false;
    g_gameRunning = running;
    std::printf("app_activity %s scene=%d flat_vis=%d flat_reg=%d dash=%d latch=%d hide=%d lasers_block=%d\n",
                frametop::AppActivityName(g_appActivity), scene ? 1 : 0, flatVis ? 1 : 0,
                flatReg ? 1 : 0, dash ? 1 : 0, g_appActivityState.flatLatch ? 1 : 0,
                g_gameRunning ? 1 : 0,
                frametop::AppBlocksOutsideGamesLasers(g_appActivity, dash) ? 1 : 0);
    std::fflush(stdout);
}

bool ModeVisible() {
    switch (EffectiveMode()) {
        case Mode::Always: return !g_manual;
        case Mode::Toggle: return g_manual;
        case Mode::Dashboard: return g_manual || vr::VROverlay()->IsDashboardVisible();
        case Mode::ExceptDashboard: {
            // Hide whenever the dashboard is open; hotkey shows them anyway. With the
            // dashboard closed, the hotkey hides them (same polarity as Always).
            if (vr::VROverlay()->IsDashboardVisible())
                return g_manual;
            return !g_manual;
        }
        case Mode::Gesture: {
            if (g_manual) return true;
            // Looking at the chosen controller: it's within the gesture angle of the gaze.
            Mat head, c;
            if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head) ||
                !DevicePose(HandDevice(g_gestureHand.c_str()), &c))
                return false;
            double f[3], to[3] = {c.m[0][3] - head.m[0][3], c.m[1][3] - head.m[1][3], c.m[2][3] - head.m[2][3]};
            Column(head, 2, f);  // the head's +Z points backward
            const double len = std::sqrt(Dot3(to, to)) + 1e-9;
            return std::acos(std::clamp(-Dot3(f, to) / len, -1.0, 1.0)) * 180 / M_PI <= g_gestureAngle;
        }
    }
    return true;
}

// The screen at its alpha; each control dimmer (kChromeIdle) unless a laser is on it or
// it's being dragged.
void ApplyAlpha(const Screen &s) {
    const float screenA = s.ComposedAlpha();
    const float chromeA = s.ChromeAlpha();
    vr::VROverlay()->SetOverlayAlpha(s.overlay, screenA);
    const auto controls = s.Controls();
    for (size_t k = 0; k < controls.size(); ++k) {
        bool active = false;
        float fill = 1.f;
        if (k == 0) active = s.hover[0] || s.drag == Drag::Move ||
                             (s.gazeHover && (g_gazeTarget.kind == GazeKind::Bar || g_gazeTarget.kind == GazeKind::Screen));
        else if (k == 1) active = s.hover[1] || (g_gazeTarget.kind == GazeKind::Curve && s.gazeHover);
        else if (k == 2) active = s.hover[2] || s.drag == Drag::Roll ||
                                  (g_gazeTarget.kind == GazeKind::Roll && s.gazeHover);
        else if (k == 3) active = s.hover[3] || s.drag == Drag::Resize ||
                                  (g_gazeTarget.kind == GazeKind::Resize && s.gazeHover);
        else if (k == 4) active = s.hoverAnchor || (g_gazeTarget.kind == GazeKind::Anchor && s.gazeHover);
        else if (k == 5) active = s.hoverDock || s.docked || (g_gazeTarget.kind == GazeKind::Dock && s.gazeHover);
        else if (s.floating && k == 6) active = s.hoverClose;
        if (controls[k] == vr::k_ulOverlayHandleInvalid) continue;
        vr::VROverlay()->SetOverlayAlpha(controls[k], chromeA * s.controls * (active ? 1.f : kChromeIdle) * fill);
    }
}

void SetVisible(Screen &s, bool visible, float visibilityFade) {
    s.visibilityFade = visibilityFade;
    if (visible) ApplyAlpha(s);
    if (visible == s.visible) {
        if (visible) ApplyAlpha(s);
        return;
    }
    s.visible = visible;
    if (visible) {
        vr::VROverlay()->ShowOverlay(s.overlay);
        for (const auto &[k, sub] : s.subs) vr::VROverlay()->ShowOverlay(sub.overlay);
        return;
    }
    // Hidden: the controls go at once (UpdateControls brings them back).
    vr::VROverlay()->HideOverlay(s.overlay);
    for (const auto &[k, sub] : s.subs) vr::VROverlay()->HideOverlay(sub.overlay);
    for (auto o : s.Controls())
        if (o != vr::k_ulOverlayHandleInvalid) vr::VROverlay()->HideOverlay(o);
    s.controls = 0, s.controlsUp = false;
}

// ---------------------------------------------------------------- eye gaze + hit testing

bool InitEyeTracking() {
    char exe[PATH_MAX] = {};
    const ssize_t n = readlink("/proc/self/exe", exe, sizeof exe - 1);
    if (n <= 0) return false;
    exe[n] = 0;
    std::string path(exe);
    const auto slash = path.rfind('/');
    if (slash == std::string::npos) return false;
    path = path.substr(0, slash) + "/actions.json";
    if (!vr::VRInput()) {
        std::fprintf(stderr, "ft-screens: no IVRInput; eye tracking unavailable\n");
        return false;
    }
    const auto err = vr::VRInput()->SetActionManifestPath(path.c_str());
    if (err != vr::VRInputError_None && err != vr::VRInputError_MismatchedActionManifest) {
        std::fprintf(stderr, "ft-screens: SetActionManifestPath(%s) failed (%d); eye tracking unavailable\n",
                     path.c_str(), int(err));
        return false;
    }
    if (vr::VRInput()->GetActionSetHandle("/actions/frametop", &g_actionSet) != vr::VRInputError_None ||
        vr::VRInput()->GetActionHandle("/actions/frametop/in/EyeGaze", &g_eyeAction) != vr::VRInputError_None) {
        std::fprintf(stderr, "ft-screens: eye gaze action handles failed\n");
        return false;
    }
    g_eyeManifestOk = true;
    std::printf("eye tracking: action manifest ready (%s)\n", path.c_str());
    return true;
}

bool SampleEyeGaze(double origin[3], double dir[3]) {
    g_eyeValid = false;
    g_eyeFlags = 0;
    if (!g_eyeManifestOk || !vr::VRInput()) return false;
    vr::VRActiveActionSet_t as{};
    as.ulActionSet = g_actionSet;
    as.ulRestrictedToDevice = vr::k_ulInvalidInputValueHandle;
    as.nPriority = 0;
    vr::VRInput()->UpdateActionState(&as, sizeof(as), 1);
    vr::VREyeTrackingData_t eye{};
    auto err =
        vr::VRInput()->GetEyeTrackingDataRelativeToNow(g_eyeAction, vr::TrackingUniverseStanding, 0.f, &eye, sizeof eye);
    if (err != vr::VRInputError_None) {
        // Some runtimes only fill next-frame data.
        err = vr::VRInput()->GetEyeTrackingDataForNextFrame(g_eyeAction, vr::TrackingUniverseStanding, &eye, sizeof eye);
    }
    g_eyeLastErr = int(err);
    if (err != vr::VRInputError_None) return false;
    g_eyeFlags = (eye.bActive ? 1 : 0) | (eye.bValid ? 2 : 0) | (eye.bTracked ? 4 : 0);
    if (!eye.bActive || !eye.bValid || !eye.bTracked) return false;
    origin[0] = eye.vGazeOrigin.v[0];
    origin[1] = eye.vGazeOrigin.v[1];
    origin[2] = eye.vGazeOrigin.v[2];
    const double dx = eye.vGazeTarget.v[0] - origin[0], dy = eye.vGazeTarget.v[1] - origin[1],
                 dz = eye.vGazeTarget.v[2] - origin[2];
    const double len = std::sqrt(dx * dx + dy * dy + dz * dz);
    if (len < 1e-5) return false;
    dir[0] = dx / len;
    dir[1] = dy / len;
    dir[2] = dz / len;
    g_eyeAvailable = true;
    g_eyeValid = true;
    return true;
}

bool SampleHeadFallbackGaze(double origin[3], double dir[3]) {
    Mat head;
    if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head)) return false;
    origin[0] = head.m[0][3];
    origin[1] = head.m[1][3];
    origin[2] = head.m[2][3];
    // Head -Z is forward in OpenVR standing space.
    dir[0] = -head.m[0][2];
    dir[1] = -head.m[1][2];
    dir[2] = -head.m[2][2];
    const double len = std::sqrt(Dot3(dir, dir)) + 1e-12;
    dir[0] /= len;
    dir[1] /= len;
    dir[2] /= len;
    return true;
}

// Ray vs axis-aligned chrome disc/bar in screen-local metres (centre origin).
bool RayHitsLocalBox(double hx, double hy, double cx, double cy, double halfW, double halfH) {
    return std::fabs(hx - cx) <= halfW && std::fabs(hy - cy) <= halfH;
}

// Defined later with the move/resize helpers; gaze hit-testing needs it here.
bool RayOnPlane(const Mat &p, const Mat &d, double *x, double *y);

GazeTarget PickGazeTarget(const double origin[3], const double dir[3]) {
    GazeTarget best;
    Mat ray = Identity();
    ray.m[0][3] = float(origin[0]);
    ray.m[1][3] = float(origin[1]);
    ray.m[2][3] = float(origin[2]);
    // Encode direction in -Z column like LaserPose (RayOnPlane uses -d.m[*][2]).
    ray.m[0][2] = float(-dir[0]);
    ray.m[1][2] = float(-dir[1]);
    ray.m[2][2] = float(-dir[2]);

    for (auto &[index, s] : g_screens) {
        if (!s.shown) continue;
        Mat p;
        if (!ScreenPose(s, &p)) continue;
        double hx, hy;
        if (!RayOnPlane(p, ray, &hx, &hy)) continue;
        const double h = s.heightMetres(), halfW = s.metres / 2, halfH = h / 2;
        const double o[3] = {origin[0], origin[1], origin[2]};
        const double hit[3] = {p.m[0][3] + float(hx) * p.m[0][0] + float(hy) * p.m[0][1],
                               p.m[1][3] + float(hx) * p.m[1][0] + float(hy) * p.m[1][1],
                               p.m[2][3] + float(hx) * p.m[2][0] + float(hy) * p.m[2][1]};
        const double dvec[3] = {hit[0] - o[0], hit[1] - o[1], hit[2] - o[2]};
        const double dist = std::sqrt(Dot3(dvec, dvec));
        if (dist >= best.distance) continue;

        auto consider = [&](GazeKind kind, int slot, double /*ignore*/) {
            if (dist >= best.distance) return;
            best.kind = kind;
            best.screen = index;
            best.slot = slot;
            best.localX = hx;
            best.localY = hy;
            best.u = halfW > 0 ? (hx + halfW) / s.metres : 0.5;
            best.v = halfH > 0 ? (halfH - hy) / h : 0.5;  // top-left pixel origin
            best.distance = dist;
        };

        const double bar = s.chrome, button = s.grip, gap = bar * 0.06;
        const double by = BarY(s);

        // Bottom chrome + slots.
        if (RayHitsLocalBox(hx, hy, 0, by, bar / 2, bar * 12 / 256)) {
            consider(GazeKind::Bar, -1, dist);
            continue;
        }
        if (RayHitsLocalBox(hx, hy, bar / 2 + gap + button / 2, by, button / 2, button / 2)) {
            consider(GazeKind::Curve, -1, dist);
            continue;
        }
        if (RayHitsLocalBox(hx, hy, bar / 2 + gap * 2 + button * 1.5, by, button / 2, button / 2)) {
            consider(GazeKind::Roll, -1, dist);
            continue;
        }
        if (RayHitsLocalBox(hx, hy, halfW + s.grip / 2, -(halfH + s.grip / 2), s.grip / 2, s.grip / 2)) {
            consider(GazeKind::Resize, -1, dist);
            continue;
        }
        if (RayHitsLocalBox(hx, hy, -(bar / 2 + gap + button / 2), by, button / 2, button / 2)) {
            consider(GazeKind::Anchor, -1, dist);
            continue;
        }
        if (RayHitsLocalBox(hx, hy, DockButtonX(s), by, button / 2, button / 2)) {
            consider(GazeKind::Dock, -1, dist);
            continue;
        }
        // Screen surface.
        if (std::fabs(hx) <= halfW && std::fabs(hy) <= halfH) consider(GazeKind::Screen, -1, dist);
    }
    // Instruments only when gaze is not already on a display/chrome. A clock/battery
    // floating near (or between you and) a screen used to steal the closest hit every
    // other frame and pulse attention + drop the gaze reticle.
    if (best.kind == GazeKind::None) {
        for (size_t ii = 0; ii < g_instruments.size(); ++ii) {
            Instrument &inst = g_instruments[ii];
            if (!inst.enabled || !inst.visible) continue;
            Mat ip;
            if (!InstrumentPose(inst, &ip)) continue;
            double hx, hy;
            if (!RayOnPlane(ip, ray, &hx, &hy)) continue;
            const double halfW = inst.metres / 2, halfH = inst.heightMetres() / 2;
            if (std::fabs(hx) > halfW || std::fabs(hy) > halfH) continue;
            const double o[3] = {origin[0], origin[1], origin[2]};
            const double hit[3] = {ip.m[0][3] + float(hx) * ip.m[0][0] + float(hy) * ip.m[0][1],
                                   ip.m[1][3] + float(hx) * ip.m[1][0] + float(hy) * ip.m[1][1],
                                   ip.m[2][3] + float(hx) * ip.m[2][0] + float(hy) * ip.m[2][1]};
            const double dvec[3] = {hit[0] - o[0], hit[1] - o[1], hit[2] - o[2]};
            const double dist = std::sqrt(Dot3(dvec, dvec));
            if (dist >= best.distance) continue;
            best.kind = GazeKind::Instrument;
            best.screen = -1;
            best.instrument = int(ii);
            best.slot = -1;
            best.localX = hx;
            best.localY = hy;
            best.u = halfW > 0 ? (hx + halfW) / inst.metres : 0.5;
            best.v = halfH > 0 ? (halfH - hy) / inst.heightMetres() : 0.5;
            best.distance = dist;
        }
    }
    PickToolbarGaze(ray, origin, &best);
    return best;
}

void UpdateGaze(double dt) {
    (void)dt;
    for (auto &[i, s] : g_screens) s.gazeHover = false;
    for (auto &inst : g_instruments) inst.gazeHover = false;
    g_eyeHeld = false;
    double origin[3], dir[3];
    bool got = SampleEyeGaze(origin, dir);
    if (got) {
        g_lastEyeValid = Clock::now();
        for (int k = 0; k < 3; ++k) g_lastEyeOrigin[k] = origin[k], g_lastEyeDir[k] = dir[k];
    } else if (g_eyeAvailable) {
        // OpenVR eye samples flicker off for tens of ms; keep the last ray so attention
        // and the gaze reticle do not pulse / vanish.
        const double since = std::chrono::duration<double>(Clock::now() - g_lastEyeValid).count();
        if (since <= kEyeSampleHoldSec) {
            for (int k = 0; k < 3; ++k) origin[k] = g_lastEyeOrigin[k], dir[k] = g_lastEyeDir[k];
            g_eyeHeld = true;
            got = true;
        }
    }
    if (!got && g_gazeFallbackHead) got = SampleHeadFallbackGaze(origin, dir);
    if (!got) {
        g_gazeTarget = {};
        return;
    }
    for (int k = 0; k < 3; ++k) g_gazeOrigin[k] = origin[k], g_gazeDir[k] = dir[k];
    g_gazeTarget = PickGazeTarget(origin, dir);
    if (g_gazeTarget) {
        if (g_gazeTarget.kind == GazeKind::Instrument && g_gazeTarget.instrument >= 0 &&
            g_gazeTarget.instrument < int(g_instruments.size())) {
            g_instruments[size_t(g_gazeTarget.instrument)].gazeHover = true;
        } else {
            auto it = g_screens.find(g_gazeTarget.screen);
            if (it != g_screens.end()) it->second.gazeHover = true;
        }
    }
    if (g_gazeDebug && (g_tick % 45) == 0) {
        const char *kind = "none";
        switch (g_gazeTarget.kind) {
            case GazeKind::Screen: kind = "screen"; break;
            case GazeKind::Bar: kind = "bar"; break;
            case GazeKind::Curve: kind = "curve"; break;
            case GazeKind::Roll: kind = "roll"; break;
            case GazeKind::Resize: kind = "resize"; break;
            case GazeKind::Anchor: kind = "anchor"; break;
            case GazeKind::Slot: kind = "slot"; break;
            case GazeKind::Instrument: kind = "instrument"; break;
            case GazeKind::Dock: kind = "dock"; break;
            case GazeKind::Toolbar: kind = "toolbar"; break;
            default: break;
        }
        std::printf("gaze: eye=%s valid=%s held=%s target=%s screen=%d u=%.3f v=%.3f dist=%.3f\n",
                    g_eyeAvailable ? "yes" : "no", g_eyeValid ? "yes" : (g_gazeFallbackHead ? "fallback" : "no"),
                    g_eyeHeld ? "yes" : "no", kind, g_gazeTarget.screen + 1, g_gazeTarget.u, g_gazeTarget.v,
                    g_gazeTarget.distance);
    }
}

void UpdateAttention(double dt) {
    for (auto &[index, s] : g_screens) {
        const float before = s.attentionResolved;
        if (!s.attentionEnabled) {
            s.attentionFocused = false;
            s.attentionFocusMs = 0;
            // No attention: show active opacity (legacy behaviour).
            s.attentionResolved = s.activeOpacity;
        } else if (!g_eyeAvailable && !g_gazeFallbackHead) {
            // Eye tracking has never delivered a sample: do not park the screen at idle
            // (that soft-locks settings UIs when idle is 0). Hold active until gaze works.
            s.attentionFocused = false;
            s.attentionFocusMs = 0;
            s.attentionResolved = s.activeOpacity;
        } else {
            // Note: while the SteamVR dashboard is open we still run normal idle/active
            // attention. Holding active there kept Frametop opaque over Steam's own UI.
            // UpdateVisibility also yields (hides) panels the user is not looking at.
            const bool hit =
                g_gazeTarget && g_gazeTarget.screen == index &&
                (g_gazeTarget.kind == GazeKind::Screen || g_gazeTarget.kind == GazeKind::Bar ||
                 g_gazeTarget.kind == GazeKind::Curve || g_gazeTarget.kind == GazeKind::Roll ||
                 g_gazeTarget.kind == GazeKind::Resize || g_gazeTarget.kind == GazeKind::Anchor ||
                 g_gazeTarget.kind == GazeKind::Dock);
            // Fresh sample, sticky held ray, or explicit head fallback all count as valid.
            const bool valid = g_eyeValid || g_eyeHeld || (g_gazeFallbackHead && g_gazeTarget);
            if (!valid) {
                // Truly lost tracking: keep focused through attentionHoldMs, then ease idle.
                // Do not slam opacity toward idle on every brief OpenVR dropout.
                if (s.attentionFocused) {
                    s.attentionFocusMs += dt * 1000.0;
                    if (s.attentionFocusMs >= s.attentionHoldMs) {
                        s.attentionFocused = false;
                        s.attentionFocusMs = 0;
                    }
                }
                const float target = s.attentionFocused ? s.activeOpacity : s.idleOpacity;
                const double tauMs = s.attentionFocused ? s.attentionInMs : s.attentionOutMs;
                const double tau = tauMs / 1000.0;
                const double a = tau <= 1e-4 ? 1.0 : 1.0 - std::exp(-dt / tau);
                s.attentionResolved = float(s.attentionResolved + (target - s.attentionResolved) * a);
            } else {
                if (hit) {
                    s.attentionFocusMs += dt * 1000.0;
                    if (!s.attentionFocused && s.attentionFocusMs >= s.attentionDwellMs) s.attentionFocused = true;
                } else if (s.attentionFocused) {
                    s.attentionFocusMs += dt * 1000.0;
                    if (s.attentionFocusMs >= s.attentionHoldMs) {
                        s.attentionFocused = false;
                        s.attentionFocusMs = 0;
                    }
                } else {
                    s.attentionFocusMs = 0;
                }
                if (hit && s.attentionFocused) s.attentionFocusMs = 0;  // reset hold while still gazing
                const float target = s.attentionFocused ? s.activeOpacity : s.idleOpacity;
                const double tauMs = s.attentionFocused ? s.attentionInMs : s.attentionOutMs;
                const double tau = tauMs / 1000.0;
                const double a = tau <= 1e-4 ? 1.0 : 1.0 - std::exp(-dt / tau);
                s.attentionResolved = float(s.attentionResolved + (target - s.attentionResolved) * a);
            }
        }
        if (std::fabs(s.attentionResolved - before) > 0.001f) {
            ApplyAlpha(s);
        }
    }
}

void SetScreenOpacity(Screen &s, float active, float idle) {
    s.activeOpacity = std::clamp(active, 0.f, 1.f);
    s.idleOpacity = std::clamp(idle, 0.f, 1.f);
    // Looking must never be dimmer than looking away (swapped sliders caused "look → vanish").
    if (s.idleOpacity > s.activeOpacity) std::swap(s.idleOpacity, s.activeOpacity);
    if (!s.attentionEnabled || (!g_eyeAvailable && !g_gazeFallbackHead))
        s.attentionResolved = s.activeOpacity;
    else
        s.attentionResolved = std::clamp(s.attentionResolved, std::min(s.idleOpacity, s.activeOpacity),
                                         std::max(s.idleOpacity, s.activeOpacity));
    PlaceChrome(s);
    ApplyAlpha(s);
}


// OpenVR draws "other application" overlays after scene overlays; within a category,
// higher SetOverlaySortOrder wins, and equal sort uses distance. Frametop is Basic /
// other-app, and Steam's dashboard UI often loses true depth to us — a farther Frametop
// screen still paints over nearer Steam/stream UI. While the dashboard is open and we
// have eye gaze, hide panels the user is not looking at (or grabbing) so Steam can own
// the foreground. Without eye tracking we only drop chrome sort order (see MakeChrome).
bool DashboardYieldActive() {
    return vr::VROverlay()->IsDashboardVisible() && (g_eyeAvailable || g_gazeFallbackHead);
}

bool GazeOnScreen(int index) {
    if (!g_gazeTarget || g_gazeTarget.screen != index) return false;
    return g_gazeTarget.kind == GazeKind::Screen || g_gazeTarget.kind == GazeKind::Bar ||
           g_gazeTarget.kind == GazeKind::Curve || g_gazeTarget.kind == GazeKind::Roll ||
           g_gazeTarget.kind == GazeKind::Resize || g_gazeTarget.kind == GazeKind::Anchor ||
           g_gazeTarget.kind == GazeKind::Dock;
}

bool GazeOnInstrument(int ii) {
    return g_gazeTarget && g_gazeTarget.instrument == ii && g_gazeTarget.kind == GazeKind::Instrument;
}

bool ScreenKeepsThroughDashboard(int index, const Screen &s) {
    if (s.drag != Drag::None) return true;
    if (GazeOnScreen(index) || s.attentionFocused) return true;
    if (s.nearUntil > g_tick) return true;
    for (bool h : s.hover)
        if (h) return true;
    if (s.hoverAnchor || s.hoverDock || s.hoverClose) return true;
    return false;
}

bool InstrumentKeepsThroughDashboard(size_t ii, const Instrument &inst) {
    if (inst.drag != Drag::None) return true;
    if (GazeOnInstrument(int(ii)) || inst.attentionFocused) return true;
    if (inst.hoverBar) return true;
    return false;
}

void ApplyOverlaySort(vr::VROverlayHandle_t o, uint32_t order, bool dash) {
    if (o == vr::k_ulOverlayHandleInvalid) return;
    // Dashboard open: force 0 so we do not sit above Steam UI via elevated chrome sort.
    vr::VROverlay()->SetOverlaySortOrder(o, dash ? 0u : order);
}

void UpdateVisibility() {
    const bool shared = ModeVisible();
    const bool dash = vr::VROverlay()->IsDashboardVisible();
    // With eye gaze: while SteamVR's dashboard (or streamed Steam UI sitting in that
    // layer) is open, hide Frametop panels the user is not looking at / grabbing.
    // OpenVR composites our Basic overlays after scene/dashboard content without true
    // cross-app depth, so a more distant Frametop screen still paints over nearer Steam UI.
    const bool yield = DashboardYieldActive();
    Mat head;
    const bool haveHead = DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head);
    for (auto &[i, s] : g_screens) {
        ApplyOverlaySort(s.overlay, 0, dash);
        for (auto o : s.Controls()) ApplyOverlaySort(o, dash ? 0 : 1, dash);

        bool visible = s.shown && (shared || s.drag != Drag::None) && !s.alone;
        // A floating window's panel: while a window floats on it, its output is on, and the
        // window isn't minimized (and once it has a crop). alone/conceal stays for real screens.
        if (s.floating) visible = visible && s.floatOn && s.outputOn && !s.minimized && s.cropW > 0;
        // Docked screens are one group with the toolbar: they hide and return with it.
        if (s.docked && !ToolbarWanted()) visible = false;
        float visFade = 1;
        Mat p;
        // Wrist fade is only for controller-pinned screens.
        if (visible && s.pinned != kNone && IsHandController(s.pinned) && s.drag == Drag::None && haveHead &&
            ScreenPose(s, &p)) {
            const double a = FacingAngle(p, head);
            visFade = float(std::clamp((g_wristAngle - a) / kFade, 0.0, 1.0));
            visible = visFade > 0.02f;
        }
        // Keep chrome interactable when the surface is fully transparent, but never for
        // concealed screens, idle float slots, or while ModeVisible says hide (e.g. a game).
        if (!visible && shared && s.shown && !s.alone && s.controls > 0.02f &&
            (!s.floating || s.floatOn) && (!s.docked || ToolbarWanted()))
            visible = true, visFade = 0.f;
        if (yield && visible && !s.docked && !ScreenKeepsThroughDashboard(i, s)) {
            visible = false;
            visFade = 0.f;
        }
        SetVisible(s, visible, visFade);
    }
}


// Controllers' lasers: OutsideGames yields for VR scenes, and for flat presentation while
// the dashboard is closed (gamepad mode). Theater + open dashboard still allows lasers.
void UpdateLasers() {
    const bool dash = vr::VROverlay()->IsDashboardVisible();
    const bool blocked = frametop::AppBlocksOutsideGamesLasers(g_appActivity, dash);
    const bool want = g_lasers == Lasers::Always || (g_lasers == Lasers::OutsideGames && !blocked);
    for (auto &[i, s] : g_screens) {
        if (s.lasers == want) continue;
        s.lasers = want;
        vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_MakeOverlaysInteractiveIfVisible, want);
        for (const auto &[k, sub] : s.subs)
            vr::VROverlay()->SetOverlayFlag(sub.overlay, vr::VROverlayFlags_MakeOverlaysInteractiveIfVisible, want);
    }
    // Media transport + instrument move bars use the same controller-laser policy.
    for (auto &inst : g_instruments) {
        if (inst.overlay != vr::k_ulOverlayHandleInvalid &&
            (inst.type == InstrumentType::Media || inst.type == InstrumentType::Launcher))
            vr::VROverlay()->SetOverlayFlag(inst.overlay, vr::VROverlayFlags_MakeOverlaysInteractiveIfVisible,
                                            want);
        if (inst.bar != vr::k_ulOverlayHandleInvalid)
            vr::VROverlay()->SetOverlayFlag(inst.bar, vr::VROverlayFlags_MakeOverlaysInteractiveIfVisible, want);
    }
}

// The controls are invisible until a laser is on one of them (SteamVR's hover event) or
// passes very close (within `reach`, about 1.5 times a button's size); they stay
// kControlsLinger ticks after it leaves, and while in use.
void UpdateControls() {
    std::vector<Mat> lasers;
    for (vr::TrackedDeviceIndex_t i = 1; i < vr::k_unMaxTrackedDeviceCount; ++i) {
        Mat d;
        if (vr::VRSystem()->GetTrackedDeviceClass(i) == vr::TrackedDeviceClass_Controller && LaserPose(i, &d))
            lasers.push_back(d);
    }
    for (auto &[i, s] : g_screens) {
        Mat p;
        if (s.visible && ScreenPose(s, &p)) {
            // Points along the bar and at each button and the tab; a laser passing within
            // `reach` of one of them is close.
            std::vector<Mat> spots;
            const auto offsets = ControlOffsets(s);
            for (double f : {-0.5, -0.25, 0.0, 0.25, 0.5})
                spots.push_back(Mul(p, Mul(offsets[0], Translation(f * s.chrome, 0, 0))));
            for (size_t k = 1; k < offsets.size(); ++k) spots.push_back(Mul(p, offsets[k]));
            const double reach = std::max(s.grip * 1.5, s.chrome * 0.12);
            for (const Mat &d : lasers) {
                const double o[3] = {d.m[0][3], d.m[1][3], d.m[2][3]}, dir[3] = {-d.m[0][2], -d.m[1][2], -d.m[2][2]};
                bool close = false;
                for (const Mat &c : spots) {
                    const double v[3] = {c.m[0][3] - o[0], c.m[1][3] - o[1], c.m[2][3] - o[2]};
                    const double t = Dot3(v, dir);
                    if (t <= 0) continue;
                    const double q[3] = {v[0] - dir[0] * t, v[1] - dir[1] * t, v[2] - dir[2] * t};
                    if (Dot3(q, q) <= reach * reach) {
                        close = true;
                        break;
                    }
                }
                if (close) {
                    s.nearUntil = g_tick + kControlsLinger;
                    break;
                }
            }
        }
        const bool anyHover =
            s.hover[0] || s.hover[1] || s.hover[2] || s.hover[3] || s.hoverAnchor || s.hoverDock || s.hoverClose;
        // Gaze drives attention fade only — chrome reveal stays laser / 3D-mouse.
        const bool inUse = s.drag != Drag::None || anyHover;
        const bool want = s.visible && (inUse || g_tick < s.nearUntil);
        // The controls stay shown while their screen is, just fully transparent when not
        // wanted: SteamVR's laser still hits them, and the hover event brings them in, for
        // any device's laser, whatever its shape.
        if (s.visible && !s.controlsUp) {
            for (auto o : s.Controls())
                if (o != vr::k_ulOverlayHandleInvalid) vr::VROverlay()->ShowOverlay(o);
            s.controlsUp = true;
            ApplyAlpha(s);
        }
        const float before = s.controls;
        s.controls = std::clamp(s.controls + (want ? 0.2f : -0.1f), 0.f, 1.f);
        if (s.controls != before) ApplyAlpha(s);
    }
}

// ---------------------------------------------------------------- moving, resizing, pinning

// Where a device's ray meets the screen's plane, in the screen's x (right) and y (up),
// metres from its centre.
bool RayOnPlane(const Mat &p, const Mat &d, double *x, double *y) {
    const double o[3] = {d.m[0][3], d.m[1][3], d.m[2][3]}, dir[3] = {-d.m[0][2], -d.m[1][2], -d.m[2][2]};
    const double c[3] = {p.m[0][3], p.m[1][3], p.m[2][3]};
    double n[3], ax[3], ay[3];
    Column(p, 2, n), Column(p, 0, ax), Column(p, 1, ay);
    const double denom = Dot3(dir, n);
    if (std::fabs(denom) < 1e-4) return false;
    const double co[3] = {c[0] - o[0], c[1] - o[1], c[2] - o[2]};
    const double t = Dot3(co, n) / denom;
    if (t <= 0) return false;
    const double rel[3] = {o[0] + dir[0] * t - c[0], o[1] + dir[1] * t - c[1], o[2] + dir[2] * t - c[2]};
    *x = Dot3(rel, ax), *y = Dot3(rel, ay);
    return true;
}
bool RayOnScreen(const Screen &s, const Mat &d, double *x, double *y) {
    Mat p;
    return ScreenPose(s, &p) && RayOnPlane(p, d, x, y);
}

// Roll: a rotation about the screen's own front axis (counterclockwise as you see it).
Mat RollZ(double rad) {
    Mat m = Identity();
    m.m[0][0] = m.m[1][1] = float(std::cos(rad));
    m.m[1][0] = float(std::sin(rad)), m.m[0][1] = float(-std::sin(rad));
    return m;
}

// Roll the screen to `rad` from its pose at the press, snapping level within kRollSnap.
void ApplyRoll(Screen &s, double rad) {
    const bool pinned = s.pinned != kNone;
    Mat c = Identity();
    if (pinned && !DevicePose(s.pinned, &c)) return;
    const Mat base = pinned ? Mul(c, s.rollFrom) : s.rollFrom;
    const Mat p = Mul(base, RollZ(rad));
    const double tilt = std::asin(std::clamp(double(p.m[1][0]), -1.0, 1.0));  // the right edge's slope
    if (std::fabs(tilt) < kRollSnap * M_PI / 180) rad -= tilt;
    if (pinned) Pin(s, s.pinned, Mul(s.rollFrom, RollZ(rad)));
    else SetAbsolute(s, Mul(base, RollZ(rad)));
}

// The laser's angle around the screen's centre, in the frame of its pose at the press.
bool RollLaserAngle(const Screen &s, const Mat &d, double *rad) {
    Mat c = Identity();
    if (s.pinned != kNone && !DevicePose(s.pinned, &c)) return false;
    const Mat base = s.pinned != kNone ? Mul(c, s.rollFrom) : s.rollFrom;
    double hx, hy;
    if (!RayOnPlane(base, d, &hx, &hy)) return false;
    *rad = std::atan2(hy, hx);
    return true;
}

// The laser while moving a screen: from the carrying device to the bar.
void Laser(const Screen &s, const Mat &d, const Mat &p, double a[3], double b[3]) {
    const Mat bar = Mul(p, BarOffset(s));
    for (int k = 0; k < 3; ++k) a[k] = d.m[k][3], b[k] = bar.m[k][3];
}

// The point q on the segment a-b closest to pt, and its distance.
double SegmentClosest(const double pt[3], const double a[3], const double b[3], double q[3]) {
    const double ab[3] = {b[0] - a[0], b[1] - a[1], b[2] - a[2]}, ap[3] = {pt[0] - a[0], pt[1] - a[1], pt[2] - a[2]};
    const double t = std::clamp(Dot3(ap, ab) / (Dot3(ab, ab) + 1e-12), 0.0, 1.0);
    for (int k = 0; k < 3; ++k) q[k] = a[k] + ab[k] * t;
    const double v[3] = {q[0] - pt[0], q[1] - pt[1], q[2] - pt[2]};
    return std::sqrt(Dot3(v, v));
}
double LaserDistance(const Screen &s, const Mat &d, const Mat &p, vr::TrackedDeviceIndex_t dev, double q[3]) {
    Mat c;
    if (!DevicePose(dev, &c)) return 1e9;
    double a[3], b[3];
    Laser(s, d, p, a, b);
    const double pt[3] = {c.m[0][3], c.m[1][3], c.m[2][3]};
    return SegmentClosest(pt, a, b, q);
}

// The hand controller (not the carrying device) whose ring the laser is in, or kNone.
vr::TrackedDeviceIndex_t WristOnLaser(const Screen &s, const Mat &d, const Mat &p) {
    for (vr::TrackedDeviceIndex_t i = 1; i < vr::k_unMaxTrackedDeviceCount; ++i) {
        double q[3];
        if (i != s.dragDevice && IsHandController(i) && LaserDistance(s, d, p, i, q) <= kWristZone) return i;
    }
    return kNone;
}

void StartDrag(Screen &s, Drag mode, vr::TrackedDeviceIndex_t dev) {
    if (s.docked && mode == Drag::Move) {
        StartToolbarDrag(dev);
        return;
    }
    if (s.docked && mode == Drag::Roll) return;
    Mat d, p;
    if (dev == kNone || !DevicePose(dev, &d) || !ScreenPose(s, &p)) return;
    s.pinTarget = kNone;
    s.dragRestore = s.anchor;
    if (s.pinned != kNone && mode == Drag::Move) {
        // Carried freely; let go, it goes back on the same wrist (unless disarmed).
        s.pinTarget = s.pinned;
        s.pinned = kNone;
        s.pose = p;
        vr::VROverlay()->SetOverlayTransformAbsolute(s.overlay, vr::TrackingUniverseStanding, &p);
        PlaceChrome(s);
    }
    s.drag = mode;
    s.dragDevice = dev;
    s.dragRel = Mul(Inverse(d), p);
    // Already in a ring when grabbed: that doesn't count as crossing it.
    s.onWrist = mode == Drag::Move ? WristOnLaser(s, d, p) : kNone;
    LightBar(s, s.pinTarget != kNone);
    if (mode == Drag::Resize) {
        double hx, hy;
        Mat l;
        if (LaserPose(dev, &l) && RayOnScreen(s, l, &hx, &hy)) s.grabX = hx - s.metres / 2, s.grabY = hy + s.heightMetres() / 2;
        else s.grabX = s.grabY = 0;
    }
    if (mode == Drag::Roll) {
        s.rollFrom = s.pinned != kNone ? s.pinRel : p;
        Mat l;
        if (!LaserPose(dev, &l) || !RollLaserAngle(s, l, &s.rollAngle)) s.drag = Drag::None, s.dragDevice = kNone;
    }
    ApplyAlpha(s);
}

// Stop moving where it is (a command took over).
void EndDrag(Screen &s) {
    s.drag = Drag::None;
    s.dragDevice = kNone;
    s.pinTarget = s.onWrist = kNone;
    LightBar(s, false);
    ApplyAlpha(s);
}

// KWin's outputs follow where the screens are, so the pointer and dragged windows cross
// to the screen you see next to this one: `ft-layout scale` runs once a move has settled.
long g_arrangeAt = -1;  // g_tick to run it at, -1 = not pending

void ArrangeDesktopSoon() { g_arrangeAt = g_tick + 45; }  // about half a second

void UpdateArrange() {
    if (g_arrangeAt < 0 || g_tick < g_arrangeAt) return;
    g_arrangeAt = -1;
    char exe[PATH_MAX];
    if (!realpath("/proc/self/exe", exe)) return;
    std::string layout(exe);  // <repo>/screens/build/ft-screens -> <repo>/layout/ft-layout
    for (int up = 0; up < 3 && layout.rfind('/') != std::string::npos; ++up) layout.resize(layout.rfind('/'));
    layout += "/layout/ft-layout";
    posix_spawn_file_actions_t io;
    posix_spawn_file_actions_init(&io);
    posix_spawn_file_actions_addopen(&io, 0, "/dev/null", O_RDONLY, 0);
    posix_spawn_file_actions_addopen(&io, 1, "/tmp/frametop-layout.log", O_WRONLY | O_CREAT | O_APPEND, 0644);
    posix_spawn_file_actions_adddup2(&io, 1, 2);
    char scale[] = "scale";
    char *argv[] = {layout.data(), scale, nullptr};
    pid_t pid;  // reaped by the compositor's SIGCHLD handler
    if (posix_spawn(&pid, layout.c_str(), &io, nullptr, argv, environ) != 0)
        std::printf("can't run %s\n", layout.c_str());
    posix_spawn_file_actions_destroy(&io);
}

// To ft-floatd (@frametop_float), for floating windows: dock, close, resize. From an unbound
// socket, so its replies go nowhere.
void SendFloat(const std::string &msg) {
    static const int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    const char name[] = "frametop_float";
    std::memcpy(addr.sun_path + 1, name, sizeof name - 1);
    sendto(fd, msg.data(), msg.size(), MSG_DONTWAIT, reinterpret_cast<sockaddr *>(&addr),
           socklen_t(offsetof(sockaddr_un, sun_path) + 1 + sizeof name - 1));
    if (msg.rfind("resize ", 0) != 0)  // an edge drag sends many resizes a second
        std::printf("to ft-floatd: %s\n", msg.c_str());
}

// Let go: pin to the armed wrist, as the screen is now.
void FinishDrag(Screen &s, int index) {
    const bool moved = s.drag == Drag::Move;
    const vr::TrackedDeviceIndex_t target = s.pinTarget;
    const AnchorMode restore = s.dragRestore;
    EndDrag(s);
    s.dragRestore = AnchorMode::World;
    Mat c, p;
    if (!moved) return;
    if (!s.floating) ArrangeDesktopSoon();
    if (target != kNone && DevicePose(target, &c) && ScreenPose(s, &p)) {
        Pin(s, target, Mul(Inverse(c), p));
        std::printf("screen %d: pinned to %s\n", index + 1, AnchorName(target));
        return;
    }
    if (IsSoftFollow(restore) && ScreenPose(s, &p)) {
        Mat hmd;
        if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &hmd)) return;
        SetFollow(s, restore, Mul(Inverse(ReferenceFrame(restore, hmd)), p));
        RefreshSlotTextures(s);
    }
}

// A button release on any of our panels ends that device's drags (it may be over another
// screen by then).
void EndDragsBy(vr::TrackedDeviceIndex_t dev) {
    keyboard::EndDragBy(dev);
    for (auto &[index, s] : g_screens)
        if (s.drag != Drag::None && s.dragDevice == dev) FinishDrag(s, index);
    EndInstrumentDragsBy(dev);
    EndToolbarDragsBy(dev);
}

// While moving: the laser entering a controller's ring flips whether the screen pins to
// it when let go (so sweeping across arms it, sweeping back disarms it).
void CheckWristAim(Screen &s, const Mat &d, const Mat &p) {
    double q[3];
    if (s.onWrist != kNone && LaserDistance(s, d, p, s.onWrist, q) > kWristLeave) s.onWrist = kNone;
    if (s.onWrist == kNone) {
        s.onWrist = WristOnLaser(s, d, p);
        if (s.onWrist != kNone) s.pinTarget = s.pinTarget == s.onWrist ? kNone : s.onWrist;
    }
    LightBar(s, s.pinTarget != kNone);
}

// Show the rings and dots for the screen being carried (hide them otherwise).
void UpdateGuides() {
    const Screen *carried = nullptr;
    Mat d, p, head;
    for (auto &[i, s] : g_screens)
        if (s.drag == Drag::Move && DevicePose(s.dragDevice, &d) && ScreenPose(s, &p)) {
            carried = &s;
            break;
        }
    if (!carried || !DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head)) {
        for (auto &[dev, g] : g_guides) g.ring.Show(false), g.dot.Show(false);
        return;
    }
    for (vr::TrackedDeviceIndex_t i = 1; i < vr::k_unMaxTrackedDeviceCount; ++i) {
        Mat c;
        const bool want = i != carried->dragDevice && IsHandController(i) && DevicePose(i, &c);
        if (!want) {
            auto it = g_guides.find(i);
            if (it != g_guides.end()) it->second.ring.Show(false), it->second.dot.Show(false);
            continue;
        }
        Guide &g = GuideFor(i);
        const double pt[3] = {c.m[0][3], c.m[1][3], c.m[2][3]};
        Mat m = FacingPose(pt, head);
        vr::VROverlay()->SetOverlayTransformAbsolute(g.ring.overlay, vr::TrackingUniverseStanding, &m);
        g.ring.Light(carried->pinTarget == i, RingTexture(carried->pinTarget == i), 128);
        g.ring.Show(true);
        double q[3];
        const double dist = LaserDistance(*carried, d, p, i, q);
        if (dist <= kDotRange) {
            m = FacingPose(q, head);
            vr::VROverlay()->SetOverlayTransformAbsolute(g.dot.overlay, vr::TrackingUniverseStanding, &m);
            g.dot.Light(dist <= kWristZone, DotTexture(dist <= kWristZone), 32);
        }
        g.dot.Show(dist <= kDotRange);
    }
}

void UpdateDrag(Screen &s, int index) {
    Mat d;
    if (!DevicePose(s.dragDevice, &d)) return;
    if (s.drag == Drag::Move) {
        const Mat p = Mul(d, s.dragRel);
        SetAbsolute(s, p);
        CheckWristAim(s, d, p);
        return;
    }
    if (s.drag == Drag::Roll) {
        // Like turning a knob: the screen turns as far as the laser has gone around its centre.
        double a;
        Mat l;
        if (!LaserPose(s.dragDevice, &l) || !RollLaserAngle(s, l, &a)) return;
        ApplyRoll(s, std::remainder(a - s.rollAngle, 2 * M_PI));
        return;
    }
    // Resize: the corner follows the ray along the screen's diagonal (so it shrinks and
    // grows from any direction), keeping where on the handle it was grabbed.
    double hx, hy;
    Mat l;
    if (!LaserPose(s.dragDevice, &l) || !RayOnScreen(s, l, &hx, &hy)) return;
    if (s.floating) {
        // A floating window: the corner goes where the laser is; ft-floatd resizes the window.
        if (s.mpp <= 0 || g_tick - s.resizeSent < 4) return;  // about 20 a second
        const double left = -s.metres / 2, top = s.heightMetres() / 2;
        const int w = std::max(320, int(std::lround((hx - s.grabX - left) / s.mpp)));
        const int h = std::max(200, int(std::lround((top - (hy - s.grabY)) / s.mpp)));
        if (w == s.resizeW && h == s.resizeH) return;
        s.resizeW = w, s.resizeH = h, s.resizeSent = g_tick;
        SendFloat("resize " + std::to_string(index + 1) + " " + std::to_string(w) + " " + std::to_string(h));
        return;
    }
    const double a = s.width > 0 ? double(s.height) / s.width : 9.0 / 16;
    const double cx = hx - s.grabX, cy = hy - s.grabY;  // where the corner should be
    SetWidth(s, 2 * (cx - a * cy) / (1 + a * a));
}

// Scroll while moving: push the screen away (up) or pull it closer, along the line from
// the head (not from the carrying device: the 3D mouse's device sits just in front of the
// bar, below the screen's centre, so that line points mostly up).
void Push(Screen &s, double notches) {
    Mat d, head;
    if (!DevicePose(s.dragDevice, &d) || !DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head)) return;
    Mat p = Mul(d, s.dragRel);
    const double to[3] = {p.m[0][3] - head.m[0][3], p.m[1][3] - head.m[1][3], p.m[2][3] - head.m[2][3]};
    const double len = std::sqrt(Dot3(to, to));
    const double next = std::clamp(len * (1 + 0.08 * notches), 0.3, 10.0);
    for (int k = 0; k < 3; ++k) p.m[k][3] = float(head.m[k][3] + to[k] / (len + 1e-9) * next);
    s.dragRel = Mul(Inverse(d), p);
}

// ---------------------------------------------------------------- floating windows

void DestroyOverlayHandle(vr::VROverlayHandle_t &o) {
    if (o == vr::k_ulOverlayHandleInvalid) return;
    vr::VROverlay()->DestroyOverlay(o);
    o = vr::k_ulOverlayHandleInvalid;
}

// Spare float slots only create the main panel at start. Chrome (bar/dock/close/…) is created
// on the first "float" and destroyed on "unfloat", so idle spares do not burn SteamVR's
// overlay budget (which also blocks valve.steam.desktopgame.* flatscreen panels).
void ReleaseFloatChrome(Screen &s) {
    if (!s.floating) return;
    DestroyOverlayHandle(s.bar);
    DestroyOverlayHandle(s.curveButton);
    DestroyOverlayHandle(s.rollButton);
    DestroyOverlayHandle(s.handle);
    DestroyOverlayHandle(s.dockButton);
    DestroyOverlayHandle(s.closeButton);
    s.controls = 0;
    s.controlsUp = false;
    s.hover[0] = s.hover[1] = s.hover[2] = s.hover[3] = false;
    s.hoverDock = s.hoverClose = false;
}

void EnsureFloatChrome(Screen &s) {
    if (!s.floating || s.bar != vr::k_ulOverlayHandleInvalid || s.floatSlot <= 0) return;
    char prefix[64], label[64], key[80], name[80];
    std::snprintf(prefix, sizeof prefix, "frametop.float.%d", s.floatSlot);
    std::snprintf(label, sizeof label, "Floating window %d", s.floatSlot);
    static const auto corner = CornerTexture(64);
    static const auto curve = CurveTexture(64);
    static const auto roll = RollTexture(64);
    static const auto dock = DockTexture(64);
    static const auto close = CloseTexture(64);
    auto chrome = [&](const char *part, const char *what, const std::vector<uint8_t> &px, int w, int h) {
        std::snprintf(key, sizeof key, "%s.%s", prefix, part);
        std::snprintf(name, sizeof name, "%s: %s", label, what);
        return MakeChrome(key, name, px, w, h);
    };
    s.bar = chrome("bar", "move", BarTexture(false), 256, 24);
    if (s.bar != vr::k_ulOverlayHandleInvalid)
        vr::VROverlay()->SetOverlayFlag(s.bar, vr::VROverlayFlags_SendVRDiscreteScrollEvents, true);
    s.curveButton = chrome("curve", "curve", curve, 64, 64);
    s.rollButton = chrome("roll", "roll", roll, 64, 64);
    if (s.rollButton != vr::k_ulOverlayHandleInvalid)
        vr::VROverlay()->SetOverlayFlag(s.rollButton, vr::VROverlayFlags_SendVRDiscreteScrollEvents, true);
    s.handle = chrome("resize", "resize", corner, 64, 64);
    s.dockButton = chrome("dock", "back to the desktop", dock, 64, 64);
    s.closeButton = chrome("close", "close", close, 64, 64);
    PlaceChrome(s);  // dock/close must get grip width immediately
    ApplyAlpha(s);
}

void CropOverlay(vr::VROverlayHandle_t o, const Screen &s, int x, int y, int w, int h) {
    if (s.width <= 0 || s.height <= 0 || w <= 0 || h <= 0) return;
    vr::VRTextureBounds_t b = {float(x) / s.width, float(y) / s.height, float(x + w) / s.width,
                               float(y + h) / s.height};
    vr::VROverlay()->SetOverlayTextureBounds(o, &b);
    vr::HmdVector2_t scale = {float(s.width), float(s.height)};
    vr::VROverlay()->SetOverlayMouseScale(o, &scale);
}

void ApplyCrop(Screen &s) {
    CropOverlay(s.overlay, s, s.cropX, s.cropY, s.cropW, s.cropH);
    for (const auto &[k, sub] : s.subs) CropOverlay(sub.overlay, s, sub.x, sub.y, sub.w, sub.h);
}

void SetFloat(Screen &s, double mpp, int x, int y, int w, int h, int title) {
    EnsureFloatChrome(s);
    const bool first = !s.floatOn || s.cropW <= 0;
    const double oldW = s.metres, oldH = s.heightMetres();
    s.floatOn = true;
    s.mpp = mpp;
    s.cropX = x, s.cropY = y, s.cropW = w, s.cropH = h, s.titleH = title;
    s.metres = w * mpp;
    vr::VROverlay()->SetOverlayWidthInMeters(s.overlay, float(s.metres));
    ApplyCurve(s);
    ApplyCrop(s);
    const double dx = (s.metres - oldW) / 2, dy = -(s.heightMetres() - oldH) / 2;
    if (!first && (std::fabs(dx) > 1e-6 || std::fabs(dy) > 1e-6)) {
        if (s.pinned != kNone) Pin(s, s.pinned, Mul(s.pinRel, Translation(dx, dy, 0)));
        else SetAbsolute(s, Mul(s.pose, Translation(dx, dy, 0)));
    } else {
        PlaceChrome(s);
    }
}

void Unfloat(Screen &s) {
    if (s.drag != Drag::None) EndDrag(s);
    for (auto &[k, sub] : s.subs) vr::VROverlay()->DestroyOverlay(sub.overlay);
    s.subs.clear();
    ReleaseFloatChrome(s);
    s.floatOn = s.minimized = s.titleCarry = false;
    s.cropW = s.cropH = 0;
    s.resizeW = s.resizeH = 0;
}

void SetSub(Screen &s, int index, int k, int x, int y, int w, int h) {
    auto it = s.subs.find(k);
    if (w <= 0 || h <= 0) {
        if (it != s.subs.end()) {
            vr::VROverlay()->DestroyOverlay(it->second.overlay);
            s.subs.erase(it);
        }
        return;
    }
    if (it == s.subs.end()) {
        Sub sub;
        char key[80], name[64];
        std::snprintf(key, sizeof key, "frametop.float.%d.sub.%d", index + 1, k);
        std::snprintf(name, sizeof name, "Floating window menu %d", k);
        if (vr::VROverlay()->CreateOverlay(key, name, &sub.overlay) != vr::VROverlayError_None) return;
        vr::VROverlay()->SetOverlayInputMethod(sub.overlay, vr::VROverlayInputMethod_Mouse);
        vr::VROverlay()->SetOverlayFlag(sub.overlay, vr::VROverlayFlags_IgnoreTextureAlpha, true);
        vr::VROverlay()->SetOverlayFlag(sub.overlay, vr::VROverlayFlags_SendVRDiscreteScrollEvents, true);
        vr::VROverlay()->SetOverlayFlag(sub.overlay, vr::VROverlayFlags_MakeOverlaysInteractiveIfVisible, s.lasers);
        vr::VROverlay()->SetOverlaySortOrder(sub.overlay, 5);
        it = s.subs.emplace(k, sub).first;
        if (s.shown) {
            auto imp = g_imports.find(s.shown);
            if (imp != g_imports.end()) {
                vr::SharedTextureHandle_t handle = imp->second;
                vr::Texture_t tex = {&handle, vr::TextureType_SharedTextureHandle, vr::ColorSpace_Gamma};
                vr::VROverlay()->SetOverlayTexture(sub.overlay, &tex);
            }
        }
        vr::VROverlay()->SetOverlayAlpha(sub.overlay, s.ComposedAlpha());
        if (s.visible) vr::VROverlay()->ShowOverlay(sub.overlay);
    }
    it->second.x = x, it->second.y = y, it->second.w = w, it->second.h = h;
    CropOverlay(it->second.overlay, s, x, y, w, h);
    PlaceSubs(s);
}

// ---------------------------------------------------------------- the catcher (minimal)
struct Press {
    vr::TrackedDeviceIndex_t device = kNone;
    uint32_t buttons = 0;
    int screen = -1;
    double x = 0, y = 0;
    double distance = 1;
    long upAt = -1;
};
Press g_press;
vr::VROverlayHandle_t g_catcher = vr::k_ulOverlayHandleInvalid;
bool g_catcherShown = false;
int g_dndLogScreen = -1;  // last screen logged while a button was held (FT_DND_DEBUG)

static bool DndDebug() {
    static int on = -1;
    if (on < 0) on = std::getenv("FT_DND_DEBUG") && std::getenv("FT_DND_DEBUG")[0] == '1' ? 1 : 0;
    return on == 1;
}

static void DndLog(const char *msg, int screen = -1) {
    if (!DndDebug()) return;
    if (screen >= 0) std::printf("dnd %s screen=%d\n", msg, screen + 1);
    else std::printf("dnd %s\n", msg);
    std::fflush(stdout);
}

uint32_t ButtonBit(uint32_t linuxButton) { return 1u << (linuxButton - BTN_LEFT); }

void PressDown(vr::TrackedDeviceIndex_t dev, uint32_t button, int screen, double x, double y) {
    if (!g_press.buttons) g_press.device = dev;
    g_press.buttons |= ButtonBit(button);
    g_press.screen = screen, g_press.x = x, g_press.y = y;
    DndLog("press", screen);
    g_dndLogScreen = screen;
}

void ReleaseAway(uint32_t button, void (*handle)(const struct ft_event *, void *), void *data) {
    if (!(g_press.buttons & ButtonBit(button))) return;
    g_press.buttons &= ~ButtonBit(button);
    if (!g_press.buttons) g_press.upAt = -1;
    if (g_press.screen < 0) return;
    ft_event e{};
    e.type = FT_BUTTON;
    e.screen = g_press.screen;
    e.button = button;
    e.pressed = false;
    e.x = g_press.x, e.y = g_press.y;
    handle(&e, data);
    std::printf("caught a release off the screens (button %u)\n", button);
    DndLog("release-away", g_press.screen);
    if (g_press.buttons) return;
    e = ft_event{};
    e.type = FT_LEAVE;
    e.screen = g_press.screen;
    handle(&e, data);
}

void ReleaseAwayBy(vr::TrackedDeviceIndex_t /*dev*/, uint32_t vrButton,
                   void (*handle)(const struct ft_event *, void *), void *data) {
    uint32_t button = BTN_LEFT;
    if (vrButton == vr::VRMouseButton_Right) button = BTN_RIGHT;
    else if (vrButton == vr::VRMouseButton_Middle) button = BTN_MIDDLE;
    ReleaseAway(button, handle, data);
}

void ShowCatcher(bool on) {
    if (on == g_catcherShown || g_catcher == vr::k_ulOverlayHandleInvalid) return;
    g_catcherShown = on;
    if (on) vr::VROverlay()->ShowOverlay(g_catcher);
    else vr::VROverlay()->HideOverlay(g_catcher);
}


void SetScreenTexture(const Screen &s, vr::SharedTextureHandle_t handle) {
    vr::Texture_t tex = {&handle, vr::TextureType_SharedTextureHandle, vr::ColorSpace_Gamma};
    vr::VROverlay()->SetOverlayTexture(s.overlay, &tex);
}

bool CutterReady() {
    if (g_cutterState) return g_cutterState > 0;
    uint64_t mods[64];
    const int n = ft_vr_modifiers(DRM_FORMAT_ABGR8888, mods, 64);
    const bool ok = g_cutter.Init(std::vector<uint64_t>(mods, mods + n), [](const handcut::Output *o) {
        auto it = g_cutImports.find(o);
        if (it == g_cutImports.end()) return;
        vr::VRIPCResourceManager()->UnrefResource(it->second);
        g_cutImports.erase(it);
    });
    g_cutterState = ok ? 1 : -1;
    std::printf(ok ? "hand cutouts ready\n" : "hand cutouts unavailable (see above)\n");
    return ok;
}

vr::SharedTextureHandle_t ImportCutout(const handcut::Output *o) {
    auto it = g_cutImports.find(o);
    if (it != g_cutImports.end()) return it->second;
    vr::DmabufAttributes_t a{};
    a.unWidth = uint32_t(o->buf.width);
    a.unHeight = uint32_t(o->buf.height);
    a.unDepth = a.unMipLevels = a.unArrayLayers = a.unSampleCount = 1;
    a.unFormat = o->buf.format;
    a.ulModifier = o->buf.modifier;
    a.unPlaneCount = uint32_t(o->buf.n_planes);
    for (int i = 0; i < o->buf.n_planes && i < int(vr::MaxDmabufPlaneCount); ++i) {
        a.plane[i].unOffset = o->buf.offset[i];
        a.plane[i].unStride = o->buf.stride[i];
        a.plane[i].nFd = o->buf.fd[i];
    }
    vr::SharedTextureHandle_t h = 0;
    if (!vr::VRIPCResourceManager()->ImportDmabuf(vr::VRApplication_Overlay, &a, &h)) {
        std::fprintf(stderr, "openvr: ImportDmabuf failed for a cutout buffer\n");
        h = 0;
    }
    g_cutImports.emplace(o, h);
    return h;
}

void StopCutting(Screen &s) {
    if (!s.cutting) return;
    vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_SideBySide_Parallel, false);
    vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_IgnoreTextureAlpha, true);
    if (s.plain) SetScreenTexture(s, s.plain);
    s.cutting = false;
}

// Floating windows don't get cutouts yet: their panel and popups show crops of the client
// buffer (texture bounds), which a side-by-side buffer doesn't match.
void UpdateCutouts() {
    Mat head;
    const bool haveHead = DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head);
    const bool hands = g_cutouts && haveHead &&
                       g_hands.Update(head, std::chrono::duration_cast<std::chrono::nanoseconds>(
                                                Clock::now().time_since_epoch()).count());
    double eyes[2][3];
    if (hands) handcut::EyePositions(head, eyes);
    for (auto &[i, s] : g_screens) {
        std::vector<handcut::Capsule2D> spots[2];
        Mat p;
        bool cut = hands && s.visible && !s.floating && s.key && s.width > 0 && ScreenPose(s, &p) &&
                   handcut::Project({p, s.metres, s.heightMetres(), s.curve, s.width, s.height}, g_hands.capsules(),
                                    eyes, spots);
        const handcut::Output *out = cut && CutterReady() ? g_cutter.Composite(i, s.key, s.buf, spots) : nullptr;
        const vr::SharedTextureHandle_t h = out ? ImportCutout(out) : 0;
        if (!h) {
            StopCutting(s);
            continue;
        }
        if (!s.cutting) {
            vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_IgnoreTextureAlpha, false);
            vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_SideBySide_Parallel, true);
            s.cutting = true;
        }
        SetScreenTexture(s, h);
    }
}

void UpdateCatcher() {
    Mat l;
    if (!g_press.buttons || g_catcher == vr::k_ulOverlayHandleInvalid || !LaserPose(g_press.device, &l)) {
        ShowCatcher(false);
        return;
    }
    vr::VROverlayIntersectionParams_t params{};
    params.eOrigin = vr::TrackingUniverseStanding;
    for (int k = 0; k < 3; ++k) params.vSource.v[k] = l.m[k][3], params.vDirection.v[k] = -l.m[k][2];
    // Nearest hit among our panels (map order alone can keep a farther source and leave the
    // catcher thinking we're still on it while a nearer destination is under the laser).
    double best = 1e9;
    for (auto &[i, s] : g_screens) {
        if (!s.visible) continue;
        std::vector<vr::VROverlayHandle_t> parts = s.All();
        for (const auto &[k, sub] : s.subs) parts.push_back(sub.overlay);
        for (auto o : parts) {
            vr::VROverlayIntersectionResults_t hit;
            if (o != vr::k_ulOverlayHandleInvalid && vr::VROverlay()->ComputeOverlayIntersection(o, &params, &hit) &&
                hit.fDistance > 0.05f && hit.fDistance < best)
                best = hit.fDistance;
        }
    }
    if (best < 1e8) {
        g_press.distance = std::max(0.05, best);
        ShowCatcher(false);
        return;
    }
    const double d = g_press.distance;
    const double pt[3] = {l.m[0][3] - l.m[0][2] * d, l.m[1][3] - l.m[1][2] * d, l.m[2][3] - l.m[2][2] * d};
    const Mat m = FacingPose(pt, l);
    vr::VROverlay()->SetOverlayTransformAbsolute(g_catcher, vr::TrackingUniverseStanding, &m);
    vr::VROverlay()->SetOverlayWidthInMeters(g_catcher, float(std::max(0.5, 2 * d)));
    ShowCatcher(true);
}

Screen *Find(int one_based) {
    auto it = g_screens.find(one_based - 1);
    return it == g_screens.end() ? nullptr : &it->second;
}

uint32_t LinuxButton(uint32_t vrButton) {
    switch (vrButton) {
        case vr::VRMouseButton_Right: return BTN_RIGHT;
        case vr::VRMouseButton_Middle: return BTN_MIDDLE;
        default: return BTN_LEFT;
    }
}

const char *LasersName() {
    switch (g_lasers) {
        case Lasers::Always: return "always";
        case Lasers::Dashboard: return "dashboard";
        default: return "outside_games";
    }
}

const char *ModeName() {
    switch (g_mode) {
        case Mode::Dashboard: return "dashboard";
        case Mode::ExceptDashboard: return "except_dashboard";
        case Mode::Gesture: return "gesture";
        case Mode::Toggle: return "toggle";
        default: return "always";
    }
}


// ---------------------------------------------------------------- Spatial Instruments

Instrument *FindInstrument(const char *id) {
    if (!id) return nullptr;
    for (auto &inst : g_instruments)
        if (inst.id == id) return &inst;
    return nullptr;
}

bool IsImageInstrumentId(const char *id) {
    if (!id) return false;
    if (!std::strcmp(id, "image")) return true;
    if (std::strncmp(id, "image-", 6) != 0) return false;
    const char *n = id + 6;
    if (!*n) return false;
    for (const char *p = n; *p; ++p)
        if (*p < '0' || *p > '9') return false;
    return std::atoi(n) >= 2;
}

bool IsLauncherInstrumentId(const char *id) {
    if (!id) return false;
    if (!std::strcmp(id, "launcher")) return true;
    if (std::strncmp(id, "launcher-", 9) != 0) return false;
    const char *n = id + 9;
    if (!*n) return false;
    for (const char *p = n; *p; ++p)
        if (*p < '0' || *p > '9') return false;
    return std::atoi(n) >= 2;
}

bool KnownInstrumentId(const char *id) {
    return id && (!std::strcmp(id, "clock") || !std::strcmp(id, "battery") || !std::strcmp(id, "storage") ||
                  !std::strcmp(id, "sd") || !std::strcmp(id, "date") || !std::strcmp(id, "media") ||
                  IsImageInstrumentId(id) || IsLauncherInstrumentId(id));
}

InstrumentType InstrumentTypeForId(const char *id) {
    if (id && !std::strcmp(id, "battery")) return InstrumentType::Battery;
    if (id && !std::strcmp(id, "storage")) return InstrumentType::Storage;
    if (id && !std::strcmp(id, "sd")) return InstrumentType::Sd;
    if (id && !std::strcmp(id, "date")) return InstrumentType::Date;
    if (id && !std::strcmp(id, "media")) return InstrumentType::Media;
    if (IsImageInstrumentId(id)) return InstrumentType::Image;
    if (IsLauncherInstrumentId(id)) return InstrumentType::Launcher;
    return InstrumentType::Clock;
}

Instrument &FindOrCreateInstrument(const char *id) {
    if (Instrument *existing = FindInstrument(id)) return *existing;
    Instrument inst;
    inst.id = id ? id : "clock";
    inst.type = InstrumentTypeForId(id);
    if (inst.type == InstrumentType::Battery) {
        inst.texW = 320;
        inst.texH = 96;
        inst.metres = 0.32;
    } else if (inst.type == InstrumentType::Storage || inst.type == InstrumentType::Sd) {
        inst.texW = 336;
        inst.texH = 96;
        inst.metres = 0.34;
    } else if (inst.type == InstrumentType::Date) {
        inst.texW = 420;
        inst.texH = 112;
        inst.metres = 0.38;
    } else if (inst.type == InstrumentType::Media) {
        inst.texW = 480;
        inst.texH = 140;
        inst.metres = 0.42;
    } else if (inst.type == InstrumentType::Image) {
        inst.texW = 384;
        inst.texH = 384;
        inst.metres = 0.50;
    } else if (inst.type == InstrumentType::Launcher) {
        inst.texW = 256;
        inst.texH = 256;
        inst.metres = 0.28;
        inst.idleOpacity = 0.55f;
        inst.launchKind = "application";
        inst.launchAppear = "fallback";
        inst.launchGlyph = "star";
    }
    g_instruments.push_back(inst);
    return g_instruments.back();
}

bool InstrumentPose(const Instrument &inst, Mat *out) {
    if (inst.pinned != kNone) {
        Mat d;
        if (!DevicePose(inst.pinned, &d)) return false;
        *out = Mul(d, inst.pinRel);
        return true;
    }
    *out = inst.pose;
    return true;
}

bool IsIdentityMat(const Mat &m) {
    const Mat id = Identity();
    for (int i = 0; i < 3; ++i)
        for (int j = 0; j < 4; ++j)
            if (std::fabs(m.m[i][j] - id.m[i][j]) > 1e-4f) return false;
    return true;
}

Mat DefaultInstrumentPose() {
    Mat head;
    if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head)) head = Identity();
    const double heading = std::atan2(head.m[0][2], head.m[2][2]) * 180 / M_PI;
    const double dx = -std::sin(heading * M_PI / 180), dz = -std::cos(heading * M_PI / 180);
    return PanelPose(head.m[0][3] + dx * 1.0, head.m[1][3] + 0.12, head.m[2][3] + dz * 1.0, heading, 0, 0);
}

double InstrumentBarY(const Instrument &inst) {
    const double chrome = std::max(0.04, inst.metres * 0.18);
    return -(inst.heightMetres() / 2 + chrome * 0.06 + chrome * 12 / 256);
}

Mat InstrumentBarOffset(const Instrument &inst) {
    return Translation(0, InstrumentBarY(inst), 0.003);
}

void PlaceInstrumentChrome(Instrument &inst) {
    if (inst.bar == vr::k_ulOverlayHandleInvalid) return;
    const double chrome = std::max(0.04, inst.metres * 0.18);
    vr::VROverlay()->SetOverlayWidthInMeters(inst.bar, float(chrome));
    const Mat offset = InstrumentBarOffset(inst);
    if (inst.pinned != kNone) {
        const Mat m = Mul(inst.pinRel, offset);
        vr::VROverlay()->SetOverlayTransformTrackedDeviceRelative(inst.bar, inst.pinned, &m);
        return;
    }
    Mat p;
    if (!InstrumentPose(inst, &p)) return;
    const Mat m = Mul(p, offset);
    vr::VROverlay()->SetOverlayTransformAbsolute(inst.bar, vr::TrackingUniverseStanding, &m);
}

void ApplyInstrumentAlpha(const Instrument &inst) {
    if (inst.overlay == vr::k_ulOverlayHandleInvalid) return;
    const float a = inst.ComposedAlpha();
    vr::VROverlay()->SetOverlayAlpha(inst.overlay, a);
    if (inst.bar != vr::k_ulOverlayHandleInvalid) {
        const bool active = inst.hoverBar || inst.drag == Drag::Move ||
                            (inst.gazeHover && g_gazeTarget.kind == GazeKind::Instrument);
        vr::VROverlay()->SetOverlayAlpha(inst.bar, a * inst.controls * (active ? 1.f : kChromeIdle));
    }
}

void LightInstrumentBar(Instrument &inst, bool lit) {
    if (inst.bar == vr::k_ulOverlayHandleInvalid || inst.barLit == lit) return;
    inst.barLit = lit;
    const auto &px = BarTexture(lit);
    vr::VROverlay()->SetOverlayRaw(inst.bar, const_cast<uint8_t *>(px.data()), 256, 24, 4);
}

void SetInstrumentAbsolute(Instrument &inst, const Mat &pose) {
    inst.anchor = AnchorMode::World;
    inst.pinned = kNone;
    inst.pose = pose;
    if (inst.overlay != vr::k_ulOverlayHandleInvalid)
        vr::VROverlay()->SetOverlayTransformAbsolute(inst.overlay, vr::TrackingUniverseStanding, &pose);
    PlaceInstrumentChrome(inst);
}

void SetInstrumentFollow(Instrument &inst, AnchorMode mode, const Mat &rel) {
    Mat seed;
    const bool haveSeed = InstrumentPose(inst, &seed);
    inst.anchor = mode;
    inst.pinRel = rel;
    if (IsRigidDevice(mode)) {
        const vr::TrackedDeviceIndex_t dev = DeviceForMode(mode);
        Mat c;
        if (dev == kNone || !DevicePose(dev, &c)) return;
        inst.pinned = dev;
        if (inst.overlay != vr::k_ulOverlayHandleInvalid)
            vr::VROverlay()->SetOverlayTransformTrackedDeviceRelative(inst.overlay, dev, &inst.pinRel);
        PlaceInstrumentChrome(inst);
        return;
    }
    inst.pinned = kNone;
    if (haveSeed) {
        inst.pose = seed;
    } else {
        Mat hmd;
        if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &hmd)) hmd = Identity();
        inst.pose = Mul(ReferenceFrame(mode, hmd), rel);
    }
    {
        Mat hmd;
        if (DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &hmd)) {
            inst.followLock = ReferenceFrame(mode, hmd);
            inst.followLockValid = true;
        } else {
            inst.followLockValid = false;
        }
    }
    if (inst.overlay != vr::k_ulOverlayHandleInvalid)
        vr::VROverlay()->SetOverlayTransformAbsolute(inst.overlay, vr::TrackingUniverseStanding, &inst.pose);
    PlaceInstrumentChrome(inst);
}

void UpdateInstrumentFollow(double dt) {
    if (dt <= 0 || dt > 0.25) return;
    Mat hmd;
    if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &hmd)) return;
    const double tau = g_followLagMs / 1000.0;
    for (auto &inst : g_instruments) {
        if (!inst.enabled || inst.drag != Drag::None || !IsSoftFollow(inst.anchor)) continue;
        // Same as UpdateFollow: only head-soft freezes under gaze.
        if (inst.attentionEnabled && inst.attentionFocused &&
            inst.anchor == AnchorMode::HeadSoft) {
            if (inst.followDeadzone) {
                const Mat cur = ReferenceFrame(inst.anchor, hmd);
                inst.followLock = cur;
                inst.followLockValid = true;
            }
            continue;
        }
        const Mat cur = ReferenceFrame(inst.anchor, hmd);
        Mat ref = cur;
        const double posFloorM = 0.025;
        const bool useDeadzone =
            inst.followDeadzone || inst.anchor == AnchorMode::PositionFollow;
        if (useDeadzone) {
            if (!inst.followLockValid) {
                inst.followLock = cur;
                inst.followLockValid = true;
            }
            const double zoneDeg = inst.followDeadzone ? inst.followDeadzoneDeg : 15.0;
            const double zoneM = inst.followDeadzone ? std::max(inst.followDeadzoneM, posFloorM)
                                                    : posFloorM;
            PushFollowLock(&inst.followLock, cur, inst.anchor, zoneDeg, zoneM);
            ref = inst.followLock;
        } else {
            inst.followLockValid = false;
        }
        const Mat target = Mul(ref, inst.pinRel);
        SmoothToward(&inst.pose, target, dt, tau);
        if (inst.overlay != vr::k_ulOverlayHandleInvalid)
            vr::VROverlay()->SetOverlayTransformAbsolute(inst.overlay, vr::TrackingUniverseStanding, &inst.pose);
        PlaceInstrumentChrome(inst);
    }
}

// 7-segment digit: bit0=A (top), B(UL), C(UR), D(mid), E(LL), F(LR), G(bot).
constexpr uint8_t kSegDigits[10] = {
    0b1110111,  // 0 ABC EFG (no D)
    0b0100100,  // 1 C F
    0b1011101,  // 2 A C D E G
    0b1101101,  // 3 A C D F G
    0b0101110,  // 4 B C D F
    0b1101011,  // 5 A B D F G
    0b1111011,  // 6 A B D E F G
    0b0100101,  // 7 A C F
    0b1111111,  // 8
    0b1101111,  // 9 A B C D F G
};

void PutInstrumentPixel(std::vector<uint8_t> &px, int w, int h, int x, int y, uint8_t r, uint8_t g, uint8_t b,
                        uint8_t a) {
    if (x < 0 || y < 0 || x >= w || y >= h) return;
    uint8_t *p = &px[(size_t(y) * w + x) * 4];
    if (a >= p[3]) {
        p[0] = r;
        p[1] = g;
        p[2] = b;
        p[3] = a;
    }
}

void FillInstrumentRect(std::vector<uint8_t> &px, int w, int h, int x0, int y0, int x1, int y1, uint8_t r, uint8_t g,
                        uint8_t b, uint8_t a) {
    if (x0 > x1) std::swap(x0, x1);
    if (y0 > y1) std::swap(y0, y1);
    for (int y = y0; y <= y1; ++y)
        for (int x = x0; x <= x1; ++x) PutInstrumentPixel(px, w, h, x, y, r, g, b, a);
}

void DrawSegDigit(std::vector<uint8_t> &px, int w, int h, int ox, int oy, int dw, int dh, int digit, uint8_t r,
                  uint8_t g, uint8_t b, uint8_t a) {
    const uint8_t bits = kSegDigits[std::clamp(digit, 0, 9)];
    const int t = std::max(2, dw / 8);
    const int mid = oy + dh / 2;
    auto segH = [&](int y) { FillInstrumentRect(px, w, h, ox + t, y - t / 2, ox + dw - t, y + t / 2, r, g, b, a); };
    auto segV = [&](int x, int y0, int y1) {
        FillInstrumentRect(px, w, h, x - t / 2, y0 + t / 2, x + t / 2, y1 - t / 2, r, g, b, a);
    };
    if (bits & 0x01) segH(oy + t);            // A
    if (bits & 0x02) segV(ox + t, oy, mid);   // B
    if (bits & 0x04) segV(ox + dw - t, oy, mid);  // C
    if (bits & 0x08) segH(mid);               // D
    if (bits & 0x10) segV(ox + t, mid, oy + dh);  // E
    if (bits & 0x20) segV(ox + dw - t, mid, oy + dh);  // F
    if (bits & 0x40) segH(oy + dh - t);       // G
}

void SoftOutlineInstrument(std::vector<uint8_t> &px, int w, int h) {
    std::vector<uint8_t> alpha(size_t(w) * h, 0);
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x) alpha[size_t(y) * w + x] = px[(size_t(y) * w + x) * 4 + 3];
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x) {
            if (alpha[size_t(y) * w + x] == 0) continue;
            for (int dy = -1; dy <= 1; ++dy)
                for (int dx = -1; dx <= 1; ++dx) {
                    if (!dx && !dy) continue;
                    const int nx = x + dx, ny = y + dy;
                    if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
                    if (alpha[size_t(ny) * w + nx] != 0) continue;
                    PutInstrumentPixel(px, w, h, nx, ny, 20, 20, 24, 160);
                }
        }
}

void RefreshClockTexture(Instrument &inst, bool force) {
    if (inst.type != InstrumentType::Clock) return;
    const std::time_t now = std::time(nullptr);
    std::tm local{};
#if defined(_WIN32)
    localtime_s(&local, &now);
#else
    localtime_r(&now, &local);
#endif
    const int minute = local.tm_hour * 60 + local.tm_min;
    if (!force && minute == inst.lastMinute && !inst.pixels.empty()) return;
    inst.lastMinute = minute;
    const int w = inst.texW, h = inst.texH;
    inst.pixels.assign(size_t(w) * h * 4, 0);
    const int digits[4] = {local.tm_hour / 10, local.tm_hour % 10, local.tm_min / 10, local.tm_min % 10};
    const int dw = 56, dh = 88, gap = 14;
    const int total = 4 * dw + 3 * gap + 18;
    int ox = (w - total) / 2;
    const int oy = (h - dh) / 2;
    for (int i = 0; i < 4; ++i) {
        if (i == 2) {
            // Colon
            const int cx = ox + 6;
            FillInstrumentRect(inst.pixels, w, h, cx, oy + dh / 3 - 4, cx + 8, oy + dh / 3 + 4, inst.colorR, inst.colorG,
                               inst.colorB, 230);
            FillInstrumentRect(inst.pixels, w, h, cx, oy + 2 * dh / 3 - 4, cx + 8, oy + 2 * dh / 3 + 4, inst.colorR,
                               inst.colorG, inst.colorB, 230);
            ox += 18;
        }
        DrawSegDigit(inst.pixels, w, h, ox, oy, dw, dh, digits[i], inst.colorR, inst.colorG, inst.colorB, 230);
        ox += dw + gap;
    }
    SoftOutlineInstrument(inst.pixels, w, h);
    if (inst.overlay != vr::k_ulOverlayHandleInvalid)
        vr::VROverlay()->SetOverlayRaw(inst.overlay, inst.pixels.data(), uint32_t(w), uint32_t(h), 4);
}

// Compact 5×7 uppercase glyphs (low 5 bits; bit4 = leftmost). Enough for weekday/month abbr.
const uint8_t *GlyphRows(char ch) {
    static const uint8_t kBlank[7] = {};
    static const uint8_t kA[7] = {0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11};
    static const uint8_t kB[7] = {0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E};
    static const uint8_t kC[7] = {0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E};
    static const uint8_t kD[7] = {0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E};
    static const uint8_t kE[7] = {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F};
    static const uint8_t kF[7] = {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10};
    static const uint8_t kG[7] = {0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0E};
    static const uint8_t kH[7] = {0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11};
    static const uint8_t kI[7] = {0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E};
    static const uint8_t kJ[7] = {0x07, 0x02, 0x02, 0x02, 0x12, 0x12, 0x0C};
    static const uint8_t kK[7] = {0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11};
    static const uint8_t kL[7] = {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F};
    static const uint8_t kM[7] = {0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11};
    static const uint8_t kN[7] = {0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11};
    static const uint8_t kO[7] = {0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E};
    static const uint8_t kP[7] = {0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10};
    static const uint8_t kQ[7] = {0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D};
    static const uint8_t kR[7] = {0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11};
    static const uint8_t kS[7] = {0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E};
    static const uint8_t kT[7] = {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04};
    static const uint8_t kU[7] = {0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E};
    static const uint8_t kV[7] = {0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04};
    static const uint8_t kW[7] = {0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11};
    static const uint8_t kX[7] = {0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11};
    static const uint8_t kY[7] = {0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04};
    static const uint8_t kZ[7] = {0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F};
    static const uint8_t k0[7] = {0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E};
    static const uint8_t k1[7] = {0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E};
    static const uint8_t k2[7] = {0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F};
    static const uint8_t k3[7] = {0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E};
    static const uint8_t k4[7] = {0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02};
    static const uint8_t k5[7] = {0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E};
    static const uint8_t k6[7] = {0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E};
    static const uint8_t k7[7] = {0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08};
    static const uint8_t k8[7] = {0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E};
    static const uint8_t k9[7] = {0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C};
    static const uint8_t kDash[7] = {0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00};
    static const uint8_t kDot[7] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C};
    static const uint8_t kColon[7] = {0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00};
    static const uint8_t kApos[7] = {0x0C, 0x0C, 0x08, 0x00, 0x00, 0x00, 0x00};
    static const uint8_t kSlash[7] = {0x01, 0x02, 0x04, 0x08, 0x10, 0x00, 0x00};
    static const uint8_t kPlus[7] = {0x00, 0x04, 0x04, 0x1F, 0x04, 0x04, 0x00};
    static const uint8_t kAnd[7] = {0x0C, 0x12, 0x14, 0x08, 0x15, 0x12, 0x0D};
    if (ch >= 'a' && ch <= 'z') ch = char(ch - 'a' + 'A');
    switch (ch) {
        case 'A': return kA;
        case 'B': return kB;
        case 'C': return kC;
        case 'D': return kD;
        case 'E': return kE;
        case 'F': return kF;
        case 'G': return kG;
        case 'H': return kH;
        case 'I': return kI;
        case 'J': return kJ;
        case 'K': return kK;
        case 'L': return kL;
        case 'M': return kM;
        case 'N': return kN;
        case 'O': return kO;
        case 'P': return kP;
        case 'Q': return kQ;
        case 'R': return kR;
        case 'S': return kS;
        case 'T': return kT;
        case 'U': return kU;
        case 'V': return kV;
        case 'W': return kW;
        case 'X': return kX;
        case 'Y': return kY;
        case 'Z': return kZ;
        case '0': return k0;
        case '1': return k1;
        case '2': return k2;
        case '3': return k3;
        case '4': return k4;
        case '5': return k5;
        case '6': return k6;
        case '7': return k7;
        case '8': return k8;
        case '9': return k9;
        case '-':
        case '_': return kDash;
        case '.': return kDot;
        case ':': return kColon;
        case '\'': return kApos;
        case '/': return kSlash;
        case '+': return kPlus;
        case '&': return kAnd;
        case ' ': return kBlank;
        default: return kBlank;
    }
}

void DrawGlyphLetter(std::vector<uint8_t> &px, int w, int h, int ox, int oy, int cell, char ch, uint8_t r,
                     uint8_t g, uint8_t b, uint8_t a) {
    const uint8_t *rows = GlyphRows(ch);
    const int scale = std::max(2, cell / 7);
    const int gw = 5 * scale, gh = 7 * scale;
    for (int row = 0; row < 7; ++row) {
        const uint8_t bits = rows[row];
        for (int col = 0; col < 5; ++col) {
            if (!(bits & (1u << (4 - col)))) continue;
            const int x0 = ox + col * scale, y0 = oy + row * scale;
            FillInstrumentRect(px, w, h, x0, y0, x0 + scale - 1, y0 + scale - 1, r, g, b, a);
        }
    }
    (void)gw;
    (void)gh;
}

void DrawGlyphWord(std::vector<uint8_t> &px, int w, int h, int ox, int oy, int cell, const char *word, uint8_t r,
                   uint8_t g, uint8_t b, uint8_t a) {
    if (!word) return;
    const int scale = std::max(2, cell / 7);
    const int advance = 5 * scale + scale;  // glyph + 1-col gap
    for (int i = 0; word[i]; ++i) DrawGlyphLetter(px, w, h, ox + i * advance, oy, cell, word[i], r, g, b, a);
}

int GlyphWordWidth(int cell, int letters) {
    const int scale = std::max(2, cell / 7);
    if (letters <= 0) return 0;
    return letters * 5 * scale + (letters - 1) * scale;
}

void RefreshDateTexture(Instrument &inst, bool force) {
    if (inst.type != InstrumentType::Date) return;
    const std::time_t now = std::time(nullptr);
    std::tm local{};
#if defined(_WIN32)
    localtime_s(&local, &now);
#else
    localtime_r(&now, &local);
#endif
    const int key = (local.tm_year + 1900) * 512 + local.tm_yday;
    if (!force && key == inst.lastDateKey && !inst.pixels.empty()) return;
    inst.lastDateKey = key;

    static const char *kDays[7] = {"SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"};
    static const char *kMonths[12] = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                      "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"};
    const char *day = kDays[std::clamp(local.tm_wday, 0, 6)];
    const char *mon = kMonths[std::clamp(local.tm_mon, 0, 11)];
    const int dom = std::clamp(local.tm_mday, 1, 31);

    const int w = inst.texW, h = inst.texH;
    inst.pixels.assign(size_t(w) * h * 4, 0);
    const int cell = 14;  // ~2px scale → readable ambient letters
    const int dw = 40, dh = 64, dgap = 8;
    const int dayW = GlyphWordWidth(cell, 3);
    const int monW = GlyphWordWidth(cell, 3);
    const int numW = 2 * dw + dgap;
    const int gap = 16;
    const int total = dayW + gap + numW + gap + monW;
    int ox = (w - total) / 2;
    const int letterOy = (h - 7 * std::max(2, cell / 7)) / 2;
    const int digitOy = (h - dh) / 2;

    const uint8_t lr = uint8_t(inst.colorR * 200 / 235), lg = uint8_t(inst.colorG * 210 / 240),
                  lb = uint8_t(inst.colorB * 220 / 245);
    DrawGlyphWord(inst.pixels, w, h, ox, letterOy, cell, day, lr, lg, lb, 220);
    ox += dayW + gap;
    DrawSegDigit(inst.pixels, w, h, ox, digitOy, dw, dh, dom / 10, inst.colorR, inst.colorG, inst.colorB, 230);
    ox += dw + dgap;
    DrawSegDigit(inst.pixels, w, h, ox, digitOy, dw, dh, dom % 10, inst.colorR, inst.colorG, inst.colorB, 230);
    ox += dw + gap;
    DrawGlyphWord(inst.pixels, w, h, ox, letterOy, cell, mon, lr, lg, lb, 220);

    SoftOutlineInstrument(inst.pixels, w, h);
    if (inst.overlay != vr::k_ulOverlayHandleInvalid)
        vr::VROverlay()->SetOverlayRaw(inst.overlay, inst.pixels.data(), uint32_t(w), uint32_t(h), 4);
}

bool ReadSysfsTrim(const std::string &path, char *buf, size_t buflen) {
    if (buflen < 2) return false;
    const int fd = open(path.c_str(), O_RDONLY | O_CLOEXEC);
    if (fd < 0) return false;
    const ssize_t n = read(fd, buf, buflen - 1);
    close(fd);
    if (n <= 0) return false;
    buf[n] = '\0';
    // Trim trailing whitespace.
    size_t len = size_t(n);
    while (len > 0 && (buf[len - 1] == '\n' || buf[len - 1] == '\r' || buf[len - 1] == ' ')) buf[--len] = '\0';
    return len > 0;
}

// Map 0–100% charge to 0–5 filled segments (20% bands; 0% → 0, 1–20 → 1, …, 81–100 → 5).
int BatteryFilledSegments(int pct) {
    pct = std::clamp(pct, 0, 100);
    if (pct <= 0) return 0;
    return std::min(5, (pct + 19) / 20);
}

void DiscoverHeadsetBatteryPath() {
    // Prefer Steam Frame Maxim fuel-gauge Battery nodes (max1720x_*); else any type=Battery with capacity.
    DIR *dir = opendir("/sys/class/power_supply");
    if (!dir) {
        g_batteryCapacityPath.clear();
        return;
    }
    std::string best, fallback;
    while (dirent *ent = readdir(dir)) {
        if (ent->d_name[0] == '.') continue;
        const std::string base = std::string("/sys/class/power_supply/") + ent->d_name;
        char type[64] = {};
        if (!ReadSysfsTrim(base + "/type", type, sizeof type)) continue;
        if (std::strcmp(type, "Battery") != 0) continue;
        const std::string cap = base + "/capacity";
        char probe[32] = {};
        if (!ReadSysfsTrim(cap, probe, sizeof probe)) continue;
        if (!std::strncmp(ent->d_name, "max1720x", 8)) {
            best = cap;
            break;
        }
        if (fallback.empty()) fallback = cap;
    }
    closedir(dir);
    g_batteryCapacityPath = !best.empty() ? best : fallback;
}

void PollHeadsetBattery() {
    const auto now = Clock::now();
    if (now < g_batteryNextPoll) return;
    g_batteryNextPoll = now + std::chrono::seconds(20);

    if (g_batteryCapacityPath.empty() || now >= g_batteryNextDiscover) {
        DiscoverHeadsetBatteryPath();
        g_batteryNextDiscover = now + std::chrono::seconds(60);
    }
    if (g_batteryCapacityPath.empty()) {
        if (g_batteryFailLogBudget > 0) {
            std::fprintf(stderr, "instrument battery: no sysfs Battery capacity node\n");
            --g_batteryFailLogBudget;
        }
        return;
    }
    char buf[32] = {};
    if (!ReadSysfsTrim(g_batteryCapacityPath, buf, sizeof buf)) {
        if (g_batteryFailLogBudget > 0) {
            std::fprintf(stderr, "instrument battery: read failed %s\n", g_batteryCapacityPath.c_str());
            --g_batteryFailLogBudget;
        }
        g_batteryCapacityPath.clear();  // rediscover next cycle
        return;
    }
    char *end = nullptr;
    long v = std::strtol(buf, &end, 10);
    if (end == buf) {
        if (g_batteryFailLogBudget > 0) {
            std::fprintf(stderr, "instrument battery: bad capacity %s\n", buf);
            --g_batteryFailLogBudget;
        }
        return;
    }
    g_batteryPct = int(std::clamp(v, 0L, 100L));
    g_batteryFailLogBudget = 3;  // recover → allow sparse logs again later
}

void RefreshBatteryTexture(Instrument &inst, bool force) {
    if (inst.type != InstrumentType::Battery) return;
    PollHeadsetBattery();
    // No invented charge: keep last texture if we never got a reading; draw empty gauge once if needed.
    const int pct = g_batteryPct;
    const int filled = pct < 0 ? 0 : BatteryFilledSegments(pct);
    // Include colour in the content key so settings colour changes force a redraw.
    const int colorKey = int(inst.colorR) * 65536 + int(inst.colorG) * 256 + int(inst.colorB);
    const int drawKey = filled * 16777216 + (colorKey & 0xFFFFFF);
    if (!force && drawKey == inst.lastBatterySeg && !inst.pixels.empty()) return;
    if (!force && pct < 0 && !inst.pixels.empty() && (inst.lastBatterySeg % 16777216) == (colorKey & 0xFFFFFF)) return;
    inst.lastBatterySeg = drawKey;
    const int w = inst.texW, h = inst.texH;
    inst.pixels.assign(size_t(w) * h * 4, 0);
    constexpr int kSegs = 5;
    const int segW = 44, segH = 36, gap = 8, radius = 4;
    const int total = kSegs * segW + (kSegs - 1) * gap;
    int ox = (w - total) / 2;
    const int oy = (h - segH) / 2;
    for (int i = 0; i < kSegs; ++i) {
        const bool on = i < filled;
        const uint8_t r = on ? inst.colorR : uint8_t(inst.colorR * 70 / 235);
        const uint8_t g = on ? inst.colorG : uint8_t(inst.colorG * 78 / 240);
        const uint8_t b = on ? inst.colorB : uint8_t(inst.colorB * 90 / 245);
        const uint8_t a = on ? 230 : 90;
        // Slightly rounded block via inset corners (simple geometry, no font).
        FillInstrumentRect(inst.pixels, w, h, ox + radius, oy, ox + segW - radius, oy + segH - 1, r, g, b, a);
        FillInstrumentRect(inst.pixels, w, h, ox, oy + radius, ox + segW - 1, oy + segH - radius - 1, r, g, b, a);
        ox += segW + gap;
    }
    SoftOutlineInstrument(inst.pixels, w, h);
    if (inst.overlay != vr::k_ulOverlayHandleInvalid)
        vr::VROverlay()->SetOverlayRaw(inst.overlay, inst.pixels.data(), uint32_t(w), uint32_t(h), 4);
}

// --- Storage (device = sum unique non-SD mounts; sd = mmcblk*, even if unmounted) ---

const char *NormalizeBlockSource(const char *src, char *out, size_t outN) {
    if (!src || !out || outN < 8 || std::strncmp(src, "/dev/", 5) != 0) return nullptr;
    size_t i = 0;
    for (; src[i] && src[i] != '[' && i + 1 < outN; ++i) out[i] = src[i];
    out[i] = 0;
    return out;
}

// 0 = ignore, 1 = device, 2 = sd
int ClassifyBlockDevice(const char *devpath) {
    if (!devpath) return 0;
    const char *base = std::strrchr(devpath, '/');
    base = base ? base + 1 : devpath;
    auto starts = [&](const char *p) { return std::strncmp(base, p, std::strlen(p)) == 0; };
    if (starts("loop") || starts("zram") || starts("nbd") || starts("ram") || starts("dm-")) return 0;
    if (starts("mmcblk") || starts("mmc")) return 2;
    if (starts("sd") || starts("nvme") || starts("vd") || starts("xvd") || starts("hd")) return 1;
    return 0;
}

bool SkipStorageFs(const char *fstype) {
    if (!fstype || !*fstype) return true;
    static const char *kSkip[] = {
        "tmpfs", "devtmpfs", "overlay", "squashfs", "proc", "sysfs", "cgroup", "cgroup2", "devpts",
        "securityfs", "pstore", "bpf", "tracefs", "debugfs", "fusectl", "configfs", "autofs",
        "fuse.portal", "functionfs", "binfmt_misc", "hugetlbfs", "mqueue", "swap", nullptr};
    for (int i = 0; kSkip[i]; ++i)
        if (!std::strcmp(fstype, kSkip[i])) return true;
    return false;
}

int StorageUsagePct(uint64_t total, uint64_t used) {
    if (total == 0) return 0;
    if (used > total) used = total;
    return int(std::min<uint64_t>(100, (used * 100 + total - 1) / total));
}

void ResetStoragePool(StoragePool *p) {
    p->present = false;
    p->mounted = false;
    p->total = 0;
    p->used = 0;
    p->pct = 0;
}

uint64_t ReadSysfsSizeBytes(const char *path) {
    // /sys/block/*/size is in 512-byte sectors.
    FILE *f = std::fopen(path, "r");
    if (!f) return 0;
    unsigned long long sectors = 0;
    const int n = std::fscanf(f, "%llu", &sectors);
    std::fclose(f);
    if (n != 1 || sectors == 0) return 0;
    return uint64_t(sectors) * 512ull;
}

void PollStoragePools() {
    const auto now = Clock::now();
    if (now < g_storageNextPoll) return;
    g_storageNextPoll = now + std::chrono::seconds(30);

    StoragePool device{}, sd{};
    ResetStoragePool(&device);
    ResetStoragePool(&sd);

    // ft-screens runs in the "dev" distrobox: host filesystems are bind-mounted under
    // /run/host (/, /home, /var, /persist, …). Prefer those so we sum SteamOS partitions,
    // not container overlay noise. On bare metal /run/host is absent and we use /proc/mounts
    // targets as-is.
    const bool hostPrefix = access("/run/host", F_OK) == 0;

    FILE *mt = std::fopen("/proc/mounts", "r");
    if (!mt) {
        if (g_storageFailLogBudget > 0) {
            std::fprintf(stderr, "instrument storage: cannot open /proc/mounts\n");
            --g_storageFailLogBudget;
        }
    } else {
        char src[512], tgt[512], fstype[64], opts[512];
        int dump = 0, pass = 0;
        std::map<std::string, bool> seen;
        while (std::fscanf(mt, "%511s %511s %63s %511s %d %d\n", src, tgt, fstype, opts, &dump, &pass) == 6) {
            if (SkipStorageFs(fstype)) continue;
            // Skip device-node bind targets and other non-fs paths from distrobox glue.
            if (!std::strncmp(tgt, "/dev/", 5)) continue;
            if (hostPrefix) {
                if (std::strcmp(tgt, "/run/host") != 0 && std::strncmp(tgt, "/run/host/", 10) != 0)
                    continue;
            }
            char norm[512];
            if (!NormalizeBlockSource(src, norm, sizeof norm)) continue;
            if (seen.count(norm)) continue;
            const int kind = ClassifyBlockDevice(norm);
            if (!kind) continue;
            struct statvfs st {};
            if (statvfs(tgt, &st) != 0 || st.f_blocks == 0 || st.f_frsize == 0) continue;
            const uint64_t total = uint64_t(st.f_blocks) * uint64_t(st.f_frsize);
            const uint64_t used = uint64_t(st.f_blocks - st.f_bfree) * uint64_t(st.f_frsize);
            seen[norm] = true;
            StoragePool *pool = kind == 2 ? &sd : &device;
            pool->present = true;
            pool->total += total;
            pool->used += used;
            if (kind == 2) pool->mounted = true;
        }
        std::fclose(mt);
    }

    // Unmounted SD cards: capacity from sysfs so the gauge still shows the card.
    if (!sd.present) {
        DIR *d = opendir("/sys/block");
        if (d) {
            while (dirent *e = readdir(d)) {
                if (e->d_name[0] == '.') continue;
                if (ClassifyBlockDevice(e->d_name) != 2) continue;
                // Whole disk only (mmcblk0), not partitions (mmcblk0p1).
                bool part = false;
                for (const char *p = e->d_name; *p; ++p) {
                    if (*p == 'p' && p > e->d_name && p[1] >= '0' && p[1] <= '9') {
                        part = true;
                        break;
                    }
                }
                if (part) continue;
                char path[PATH_MAX];
                std::snprintf(path, sizeof path, "/sys/block/%s/size", e->d_name);
                const uint64_t bytes = ReadSysfsSizeBytes(path);
                if (bytes == 0) continue;
                sd.present = true;
                sd.total = bytes;
                sd.used = 0;
                sd.mounted = false;
                break;
            }
            closedir(d);
        }
    }

    device.pct = StorageUsagePct(device.total, device.used);
    sd.pct = StorageUsagePct(sd.total, sd.used);
    g_storageDevice = device;
    g_storageSd = sd;
    g_storageFailLogBudget = 3;
}

void DrawStorageGlyph(std::vector<uint8_t> &px, int w, int h, int ox, int oy, bool sdCard, uint8_t r, uint8_t g,
                      uint8_t b, uint8_t a) {
    // Tiny ambient icons: filled square = device disk; notched rectangle = SD.
    if (!sdCard) {
        FillInstrumentRect(px, w, h, ox, oy, ox + 18, oy + 18, r, g, b, a);
        FillInstrumentRect(px, w, h, ox + 5, oy + 5, ox + 13, oy + 13, 20, 22, 28, 200);
        return;
    }
    FillInstrumentRect(px, w, h, ox + 2, oy, ox + 16, oy + 20, r, g, b, a);
    FillInstrumentRect(px, w, h, ox, oy + 4, ox + 4, oy + 10, r, g, b, a);  // contact notch
    FillInstrumentRect(px, w, h, ox + 6, oy + 4, ox + 12, oy + 8, 20, 22, 28, 200);
}

void RefreshStorageTexture(Instrument &inst, bool force) {
    if (inst.type != InstrumentType::Storage && inst.type != InstrumentType::Sd) return;
    PollStoragePools();
    const StoragePool &pool = inst.type == InstrumentType::Sd ? g_storageSd : g_storageDevice;
    const int key = pool.present ? (1000 + pool.pct + (pool.mounted ? 0 : 200)) : 0;
    if (!force && key == inst.lastStorageKey && !inst.pixels.empty()) return;
    inst.lastStorageKey = key;
    const int w = inst.texW, h = inst.texH;
    inst.pixels.assign(size_t(w) * h * 4, 0);

    const bool hot = pool.present && pool.pct >= 85;
    const uint8_t tr = hot ? 235 : 70, tg = hot ? 150 : 78, tb = hot ? 90 : 95, ta = pool.present ? 110 : 50;
    const uint8_t fr = hot ? 240 : 120, fg = hot ? 170 : 210, fb = hot ? 100 : 230,
                  fa = pool.present ? 235 : 70;

    const int barX0 = 44, barX1 = w - 16, barY0 = (h - 28) / 2, barY1 = barY0 + 27, rad = 4;
    // Track
    FillInstrumentRect(inst.pixels, w, h, barX0 + rad, barY0, barX1 - rad, barY1, tr, tg, tb, ta);
    FillInstrumentRect(inst.pixels, w, h, barX0, barY0 + rad, barX1, barY1 - rad, tr, tg, tb, ta);
    if (pool.present && pool.total > 0) {
        const int fillW = int((int64_t(barX1 - barX0) * pool.pct) / 100);
        if (fillW > 0) {
            const int fx1 = barX0 + std::max(fillW, rad + 1);
            FillInstrumentRect(inst.pixels, w, h, barX0 + rad, barY0 + 3, fx1 - rad, barY1 - 3, fr, fg, fb, fa);
            FillInstrumentRect(inst.pixels, w, h, barX0 + 3, barY0 + rad, fx1 - 3, barY1 - rad, fr, fg, fb, fa);
        }
        // Unmounted SD: soft mid stripe so the empty capacity still reads as "card present".
        if (inst.type == InstrumentType::Sd && !pool.mounted) {
            FillInstrumentRect(inst.pixels, w, h, barX0 + 8, barY0 + 12, barX1 - 8, barY0 + 15, 180, 190, 200, 90);
        }
    }
    DrawStorageGlyph(inst.pixels, w, h, 12, (h - 20) / 2, inst.type == InstrumentType::Sd, fr, fg, fb,
                     pool.present ? 220 : 80);
    SoftOutlineInstrument(inst.pixels, w, h);
    if (inst.overlay != vr::k_ulOverlayHandleInvalid)
        vr::VROverlay()->SetOverlayRaw(inst.overlay, inst.pixels.data(), uint32_t(w), uint32_t(h), 4);
}

// --- Media (MPRIS via @frametop_mpris host bridge) ---

Clock::time_point g_mediaNextPoll{};
int g_mediaFailLogBudget = 3;

bool AskFrametopMpris(const char *cmd, char *reply, size_t replyN) {
    if (!cmd || !reply || replyN < 8) return false;
    reply[0] = 0;
    const int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return false;
    sockaddr_un local{};
    local.sun_family = AF_UNIX;
    // Abstract autobind: sun_path[0]=0, rest zero → kernel assigns.
    if (bind(fd, reinterpret_cast<sockaddr *>(&local), sizeof(sa_family_t)) != 0) {
        close(fd);
        return false;
    }
    timeval tv{};
    tv.tv_sec = 0;
    tv.tv_usec = 400000;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    sockaddr_un dest{};
    dest.sun_family = AF_UNIX;
    dest.sun_path[0] = '\0';
    const char kName[] = "frametop_mpris";
    std::memcpy(dest.sun_path + 1, kName, sizeof kName - 1);
    const socklen_t destLen = socklen_t(offsetof(sockaddr_un, sun_path) + 1 + sizeof kName - 1);
    const ssize_t sent = sendto(fd, cmd, std::strlen(cmd), 0, reinterpret_cast<sockaddr *>(&dest), destLen);
    if (sent < 0) {
        close(fd);
        return false;
    }
    const ssize_t n = recvfrom(fd, reply, replyN - 1, 0, nullptr, nullptr);
    close(fd);
    if (n <= 0) return false;
    reply[n] = 0;
    return true;
}

void PollMediaBridge(Instrument &inst) {
    const auto now = Clock::now();
    // Always rate-limit — polling every frame when idle hammered the bridge and flickered.
    if (now < g_mediaNextPoll) return;
    g_mediaNextPoll = now + std::chrono::milliseconds(500);
    char reply[512];
    if (!AskFrametopMpris("state", reply, sizeof reply)) {
        if (g_mediaFailLogBudget > 0) {
            std::fprintf(stderr, "instrument media: @frametop_mpris not reachable\n");
            --g_mediaFailLogBudget;
        }
        return;  // keep last-known text/status on transient failures
    }
    g_mediaFailLogBudget = 3;
    // ok <status> <prev> <pp> <next> <text...>
    char status[32] = {};
    int prev = 0, pp = 0, next = 0;
    if (std::sscanf(reply, "ok %31s %d %d %d", status, &prev, &pp, &next) < 4) {
        return;
    }
    // Text starts after the fourth token.
    const char *rest = reply;
    for (int i = 0; i < 5 && rest && *rest; ++i) {
        while (*rest == ' ') ++rest;
        while (*rest && *rest != ' ') ++rest;
    }
    while (rest && *rest == ' ') ++rest;
    inst.mediaCanPrev = prev != 0;
    inst.mediaCanPause = pp != 0;
    inst.mediaCanNext = next != 0;
    if (!std::strcmp(status, "playing"))
        inst.mediaStatus = 3;
    else if (!std::strcmp(status, "paused"))
        inst.mediaStatus = 2;
    else if (!std::strcmp(status, "stopped"))
        inst.mediaStatus = 1;
    else
        inst.mediaStatus = 0;
    const std::string nextText = (!rest || !*rest || !std::strcmp(status, "none")) ? "" : rest;
    if (nextText != inst.mediaText) {
        inst.mediaText = nextText;
        inst.mediaScroll = 0;
        inst.mediaScrollAcc = 0;
    }
}

void MediaSend(const char *cmd) {
    char reply[512];
    AskFrametopMpris(cmd, reply, sizeof reply);
    g_mediaNextPoll = Clock::time_point{};  // force refresh
}

void DrawMediaIcon(std::vector<uint8_t> &px, int w, int h, int cx, int cy, int kind, bool on,
                   uint8_t cr, uint8_t cg, uint8_t cb) {
    // kind: 0=prev, 1=play, 2=pause, 3=next. Simple geometric glyphs.
    const uint8_t r = on ? cr : uint8_t(cr * 90 / 255);
    const uint8_t g = on ? cg : uint8_t(cg * 90 / 255);
    const uint8_t b = on ? cb : uint8_t(cb * 90 / 255);
    const uint8_t a = on ? 230 : 100;
    const int s = 14;
    if (kind == 0) {  // |<
        FillInstrumentRect(px, w, h, cx - s, cy - s / 2, cx - s + 3, cy + s / 2, r, g, b, a);
        for (int i = 0; i < s; ++i)
            FillInstrumentRect(px, w, h, cx - i, cy - i / 2, cx - i + 2, cy + i / 2, r, g, b, a);
    } else if (kind == 1) {  // >
        for (int i = 0; i < s; ++i)
            FillInstrumentRect(px, w, h, cx - s / 2 + i, cy - (s - i) / 2, cx - s / 2 + i + 2, cy + (s - i) / 2, r, g,
                               b, a);
    } else if (kind == 2) {  // ||
        FillInstrumentRect(px, w, h, cx - 8, cy - s / 2, cx - 3, cy + s / 2, r, g, b, a);
        FillInstrumentRect(px, w, h, cx + 3, cy - s / 2, cx + 8, cy + s / 2, r, g, b, a);
    } else {  // >|
        for (int i = 0; i < s; ++i)
            FillInstrumentRect(px, w, h, cx + i - s / 2, cy - i / 2, cx + i - s / 2 + 2, cy + i / 2, r, g, b, a);
        FillInstrumentRect(px, w, h, cx + s / 2 - 1, cy - s / 2, cx + s / 2 + 2, cy + s / 2, r, g, b, a);
    }
}

void RefreshMediaTexture(Instrument &inst, bool force) {
    if (inst.type != InstrumentType::Media) return;
    PollMediaBridge(inst);
    const int cell = 10;
    const int textW = GlyphWordWidth(cell, int(inst.mediaText.size()));
    const int viewW = inst.texW - 24;
    const bool scroll = textW > viewW && !inst.mediaText.empty();
    // Slow marquee: advance ~6–12 px/s, but only re-upload every 2 px to cut SetOverlayRaw churn.
    if (scroll) {
        inst.mediaScrollAcc += (inst.mediaStatus == 3 ? 0.12 : 0.06);
        if (inst.mediaScrollAcc >= 2.0) {
            const int step = int(inst.mediaScrollAcc);
            inst.mediaScrollAcc -= step;
            inst.mediaScroll += step;
        }
        if (inst.mediaScroll > textW + 40) inst.mediaScroll = -20;
    } else {
        inst.mediaScroll = 0;
        inst.mediaScrollAcc = 0;
    }
    const int scrollPx = int(inst.mediaScroll);
    const int key = int(inst.mediaStatus) * 1000003 + int(inst.mediaCanPrev) * 17 + int(inst.mediaCanNext) * 31 +
                    int(inst.mediaCanPause) * 13 + int(inst.mediaText.size()) * 101 +
                    int(inst.colorR) * 65536 + int(inst.colorG) * 256 + int(inst.colorB) +
                    (inst.mediaText.empty() ? 0 : int(unsigned(inst.mediaText[0])) * 13 +
                     (inst.mediaText.size() > 1 ? int(unsigned(inst.mediaText.back())) : 0));
    if (!force && key == inst.lastMediaKey && scrollPx == inst.lastMediaScrollPx && !inst.pixels.empty()) return;
    inst.lastMediaKey = key;
    inst.lastMediaScrollPx = scrollPx;

    const int w = inst.texW, h = inst.texH;
    inst.pixels.assign(size_t(w) * h * 4, 0);
    const int letterOy = 18;
    const uint8_t tr = inst.colorR, tg = inst.colorG, tb = inst.colorB;
    if (inst.mediaText.empty()) {
        DrawGlyphWord(inst.pixels, w, h, 24, letterOy, cell, "NO MEDIA",
                      uint8_t(tr * 120 / 255), uint8_t(tg * 125 / 255), uint8_t(tb * 135 / 255), 180);
    } else if (!scroll) {
        DrawGlyphWord(inst.pixels, w, h, (w - textW) / 2, letterOy, cell, inst.mediaText.c_str(), tr, tg, tb, 230);
    } else {
        const int ox = 12 - scrollPx;
        DrawGlyphWord(inst.pixels, w, h, ox, letterOy, cell, inst.mediaText.c_str(), tr, tg, tb, 230);
    }
    // Glyphs only — no filled transport bar. The opaque strip flickered under marquee
    // SetOverlayRaw uploads the same way SoftOutline did.
    const int by = h - 48;
    const int third = w / 3;
    const bool playing = inst.mediaStatus == 3;
    DrawMediaIcon(inst.pixels, w, h, third / 2, by + 18, 0, inst.mediaCanPrev, tr, tg, tb);
    DrawMediaIcon(inst.pixels, w, h, third + third / 2, by + 18, playing ? 2 : 1, inst.mediaCanPause || playing, tr,
                   tg, tb);
    DrawMediaIcon(inst.pixels, w, h, 2 * third + third / 2, by + 18, 3, inst.mediaCanNext, tr, tg, tb);
    // SoftOutline every marquee frame caused visible flicker — skip for Media.
    if (inst.overlay != vr::k_ulOverlayHandleInvalid) {
        vr::HmdVector2_t scale = {(float)w, (float)h};
        vr::VROverlay()->SetOverlayMouseScale(inst.overlay, &scale);
        vr::VROverlay()->SetOverlayRaw(inst.overlay, inst.pixels.data(), uint32_t(w), uint32_t(h), 4);
    }
}

int MediaHitButton(const Instrument &inst, double mx, double my) {
    // Returns 0=prev 1=playpause 2=next, or -1.
    // OpenVR mouse is bottom-left (same as screens); draw code uses top-left.
    if (inst.type != InstrumentType::Media) return -1;
    const double w = inst.texW, h = inst.texH;
    double x = mx, y = my;
    if (mx <= 1.01 && my <= 1.01) {
        x = mx * w;
        y = my * h;
    }
    y = h - y;  // bottom-left → top-left
    if (y < h - 48.0) return -1;  // marquee / upper panel
    const int third = inst.texW / 3;
    if (x < third) return 0;
    if (x < 2 * third) return 1;
    return 2;
}

void PollMediaOverlay(Instrument &inst) {
    if (inst.type != InstrumentType::Media || inst.overlay == vr::k_ulOverlayHandleInvalid) return;
    vr::VREvent_t ev;
    while (vr::VROverlay()->PollNextOverlayEvent(inst.overlay, &ev, sizeof ev)) {
        if (ev.eventType != vr::VREvent_MouseButtonDown || ev.data.mouse.button != vr::VRMouseButton_Left) continue;
        const int btn = MediaHitButton(inst, ev.data.mouse.x, ev.data.mouse.y);
        if (btn == 0 && inst.mediaCanPrev)
            MediaSend("previous");
        else if (btn == 1 && (inst.mediaCanPause || inst.mediaStatus > 0))
            MediaSend("playpause");
        else if (btn == 2 && inst.mediaCanNext)
            MediaSend("next");
        PollMediaBridge(inst);
        RefreshMediaTexture(inst, true);
    }
}

// --- Launcher (spatial app / action / command shortcut via @frametop_launch) ---

bool AskFrametopLaunch(const char *cmd, char *reply, size_t replyN) {
    if (!cmd || !reply || replyN < 8) return false;
    reply[0] = 0;
    const int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return false;
    sockaddr_un local{};
    local.sun_family = AF_UNIX;
    if (bind(fd, reinterpret_cast<sockaddr *>(&local), sizeof(sa_family_t)) != 0) {
        close(fd);
        return false;
    }
    timeval tv{};
    tv.tv_sec = 0;
    tv.tv_usec = 800000;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    sockaddr_un dest{};
    dest.sun_family = AF_UNIX;
    dest.sun_path[0] = '\0';
    const char kName[] = "frametop_launch";
    std::memcpy(dest.sun_path + 1, kName, sizeof kName - 1);
    const socklen_t destLen = socklen_t(offsetof(sockaddr_un, sun_path) + 1 + sizeof kName - 1);
    const ssize_t sent = sendto(fd, cmd, std::strlen(cmd), 0, reinterpret_cast<sockaddr *>(&dest), destLen);
    if (sent < 0) {
        close(fd);
        return false;
    }
    const ssize_t n = recvfrom(fd, reply, replyN - 1, 0, nullptr, nullptr);
    close(fd);
    if (n <= 0) return false;
    reply[n] = 0;
    return true;
}

void DrawLauncherGlyph(std::vector<uint8_t> &px, int w, int h, const std::string &glyph, uint8_t r, uint8_t g,
                       uint8_t b, uint8_t a) {
    const int cx = w / 2, cy = h / 2;
    const int s = std::min(w, h) / 5;
    auto disc = [&](int x, int y, int rad) {
        for (int yy = -rad; yy <= rad; ++yy)
            for (int xx = -rad; xx <= rad; ++xx)
                if (xx * xx + yy * yy <= rad * rad) PutInstrumentPixel(px, w, h, x + xx, y + yy, r, g, b, a);
    };
    const std::string gname = glyph.empty() ? "star" : glyph;
    if (gname == "play") {
        for (int i = 0; i < s; ++i)
            FillInstrumentRect(px, w, h, cx - s / 2 + i, cy - (s - i) / 2, cx - s / 2 + i + 3, cy + (s - i) / 2, r, g,
                               b, a);
    } else if (gname == "stop") {
        FillInstrumentRect(px, w, h, cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2, r, g, b, a);
    } else if (gname == "home") {
        FillInstrumentRect(px, w, h, cx - s / 2, cy - s / 6, cx + s / 2, cy + s / 2, r, g, b, a);
        for (int i = 0; i < s; ++i)
            FillInstrumentRect(px, w, h, cx - s + i, cy - i / 2, cx + s - i, cy - i / 2 + 3, r, g, b, a);
    } else if (gname == "gear") {
        disc(cx, cy, s / 2);
        for (int k = 0; k < 6; ++k) {
            const double ang = k * 3.14159265 / 3.0;
            const int x = cx + int(std::cos(ang) * s * 0.75);
            const int y = cy + int(std::sin(ang) * s * 0.75);
            disc(x, y, s / 5);
        }
    } else if (gname == "moon") {
        disc(cx, cy, s / 2 + 2);
        for (int yy = -s; yy <= s; ++yy)
            for (int xx = -s; xx <= s; ++xx)
                if (xx * xx + yy * yy <= (s / 2) * (s / 2))
                    PutInstrumentPixel(px, w, h, cx + xx + s / 4, cy + yy - s / 8, 0, 0, 0, 0);
    } else if (gname == "music") {
        FillInstrumentRect(px, w, h, cx - 2, cy - s / 2, cx + 2, cy + s / 3, r, g, b, a);
        disc(cx - s / 3, cy + s / 3, s / 4);
        disc(cx + s / 4, cy + s / 5, s / 5);
    } else if (gname == "terminal") {
        FillInstrumentRect(px, w, h, cx - s, cy - s / 2, cx + s, cy + s / 2, r, g, b, uint8_t(a * 40 / 255));
        for (int i = 0; i < s / 2; ++i)
            FillInstrumentRect(px, w, h, cx - s / 2 + i, cy - s / 4 + i / 2, cx - s / 2 + i + 2, cy - s / 4 + i / 2 + 2,
                               r, g, b, a);
        FillInstrumentRect(px, w, h, cx - s / 6, cy + s / 4, cx + s / 2, cy + s / 4 + 3, r, g, b, a);
    } else if (gname == "arrow") {
        for (int i = 0; i < s; ++i)
            FillInstrumentRect(px, w, h, cx - s / 2 + i, cy - 2, cx - s / 2 + i + 2, cy + 2, r, g, b, a);
        for (int i = 0; i < s / 2; ++i)
            FillInstrumentRect(px, w, h, cx + s / 2 - i, cy - s / 2 + i, cx + s / 2 - i + 3, cy + s / 2 - i, r, g, b, a);
    } else if (gname == "power") {
        disc(cx, cy, s / 2);
        FillInstrumentRect(px, w, h, cx - 2, cy - s / 2 - 2, cx + 2, cy, r, g, b, a);
    } else {  // star (default) / fallback
        for (int k = 0; k < 5; ++k) {
            const double ang = -3.14159265 / 2 + k * 2.0 * 3.14159265 / 5.0;
            const int x = cx + int(std::cos(ang) * s * 0.7);
            const int y = cy + int(std::sin(ang) * s * 0.7);
            FillInstrumentRect(px, w, h, std::min(cx, x), std::min(cy, y), std::max(cx, x) + 2, std::max(cy, y) + 2, r,
                               g, b, a);
        }
        disc(cx, cy, s / 4);
    }
}

void RefreshLauncherTexture(Instrument &inst, bool force) {
    if (inst.type != InstrumentType::Launcher) return;
    const bool useImage = (inst.launchAppear == "app" || inst.launchAppear == "image") && !inst.imageFrames.empty();
    const int key = int(inst.launchAppear.size()) * 17 + int(inst.launchGlyph.size()) * 31 +
                    int(inst.imageFrames.size()) * 101 + (useImage ? 1 : 0) + int(inst.gazeHover) * 7 +
                    int(inst.attentionFocused) * 13;
    if (!force && key == inst.lastLauncherKey && !inst.pixels.empty()) return;
    inst.lastLauncherKey = key;

    if (useImage) {
        const int fi = std::clamp(inst.imageFrame, 0, int(inst.imageFrames.size()) - 1);
        const ImageFrame &frame = inst.imageFrames[size_t(fi)];
        if (frame.rgba.size() == size_t(inst.texW) * size_t(inst.texH) * 4) {
            inst.pixels = frame.rgba;
        } else {
            inst.pixels = frame.rgba;
            const size_t n = frame.rgba.size() / 4;
            int side = int(std::sqrt(double(n)));
            while (side > 1 && size_t(side) * size_t(side) != n) --side;
            if (size_t(side) * size_t(side) == n) {
                inst.texW = side;
                inst.texH = side;
            }
        }
        if (inst.overlay != vr::k_ulOverlayHandleInvalid) {
            vr::HmdVector2_t scale = {(float)inst.texW, (float)inst.texH};
            vr::VROverlay()->SetOverlayMouseScale(inst.overlay, &scale);
            vr::VROverlay()->SetOverlayRaw(inst.overlay, inst.pixels.data(), uint32_t(inst.texW), uint32_t(inst.texH),
                                           4);
        }
        return;
    }

    inst.texW = 256;
    inst.texH = 256;
    const int w = inst.texW, h = inst.texH;
    inst.pixels.assign(size_t(w) * h * 4, 0);
    const uint8_t tr = inst.colorR, tg = inst.colorG, tb = inst.colorB;
    const uint8_t a = inst.attentionFocused || inst.gazeHover ? 240 : 200;
    const std::string glyph =
        (inst.launchAppear == "glyph" && !inst.launchGlyph.empty()) ? inst.launchGlyph : std::string("star");
    DrawLauncherGlyph(inst.pixels, w, h, glyph, tr, tg, tb, a);
    if (inst.overlay != vr::k_ulOverlayHandleInvalid) {
        vr::HmdVector2_t scale = {(float)w, (float)h};
        vr::VROverlay()->SetOverlayMouseScale(inst.overlay, &scale);
        vr::VROverlay()->SetOverlayRaw(inst.overlay, inst.pixels.data(), uint32_t(w), uint32_t(h), 4);
    }
}

void ActivateLauncher(Instrument &inst) {
    if (inst.type != InstrumentType::Launcher) return;
    char reply[512];
    std::string cmd;
    if (inst.launchKind == "action") {
        if (inst.launchTarget.empty() || inst.launchTarget == "-") {
            std::fprintf(stderr, "instrument launcher %s: no semantic action\n", inst.id.c_str());
            return;
        }
        cmd = "action " + inst.launchTarget;
    } else if (inst.launchKind == "shell") {
        if (inst.launchTarget.empty()) {
            std::fprintf(stderr, "instrument launcher %s: empty shell\n", inst.id.c_str());
            return;
        }
        cmd = "shell " + inst.launchTarget;
    } else if (inst.launchKind == "command") {
        if (inst.launchCommandJson.empty()) {
            std::fprintf(stderr, "instrument launcher %s: empty command\n", inst.id.c_str());
            return;
        }
        cmd = "command " + inst.launchCommandJson;
    } else {
        if (inst.launchTarget.empty() || inst.launchTarget == "-") {
            std::fprintf(stderr, "instrument launcher %s: no desktop id\n", inst.id.c_str());
            return;
        }
        cmd = "desktop " + inst.launchTarget;
    }
    if (!AskFrametopLaunch(cmd.c_str(), reply, sizeof reply)) {
        std::fprintf(stderr, "instrument launcher %s: @frametop_launch not reachable\n", inst.id.c_str());
        return;
    }
    if (std::strncmp(reply, "ok", 2) != 0)
        std::fprintf(stderr, "instrument launcher %s: %s\n", inst.id.c_str(), reply);
}

void PollLauncherOverlay(Instrument &inst) {
    if (inst.type != InstrumentType::Launcher || inst.overlay == vr::k_ulOverlayHandleInvalid) return;
    vr::VREvent_t ev;
    while (vr::VROverlay()->PollNextOverlayEvent(inst.overlay, &ev, sizeof ev)) {
        if (ev.eventType != vr::VREvent_MouseButtonDown || ev.data.mouse.button != vr::VRMouseButton_Left) continue;
        ActivateLauncher(inst);
    }
}

// --- Image instrument (PNG/JPEG stills + animated GIF; RGBA alpha preserved) ---

static constexpr int kImageMaxEdge = 768;       // keep overlays light; big GIFs OOM'd ft-screens
static constexpr int kImageMaxFrames = 48;
static constexpr size_t kImageMaxDecodedBytes = 48ull * 1024ull * 1024ull;  // full-res decode cap

void ScaleRgbaNearest(const uint8_t *src, int sw, int sh, uint8_t *dst, int dw, int dh) {
    for (int y = 0; y < dh; ++y) {
        const int sy = y * sh / dh;
        for (int x = 0; x < dw; ++x) {
            const int sx = x * sw / dw;
            const uint8_t *s = src + (size_t(sy) * sw + sx) * 4;
            uint8_t *d = dst + (size_t(y) * dw + x) * 4;
            d[0] = s[0];
            d[1] = s[1];
            d[2] = s[2];
            d[3] = s[3];
        }
    }
}

void ImageTargetSize(int sw, int sh, int *dw, int *dh) {
    int w = std::max(1, sw), h = std::max(1, sh);
    const int edge = std::max(w, h);
    if (edge > kImageMaxEdge) {
        w = std::max(1, (w * kImageMaxEdge + edge / 2) / edge);
        h = std::max(1, (h * kImageMaxEdge + edge / 2) / edge);
    }
    *dw = w;
    *dh = h;
}

void ClearImageFrames(Instrument &inst) {
    inst.imageFrames.clear();
    inst.imageFrame = 0;
    inst.imageFrameAccMs = 0;
    inst.lastImageFrame = -1;
}

void DrawImagePlaceholder(Instrument &inst) {
    inst.texW = 384;
    inst.texH = 384;
    const int w = inst.texW, h = inst.texH;
    inst.pixels.assign(size_t(w) * h * 4, 0);
    // Soft translucent plate so an empty Image still has a grab target.
    for (int y = 16; y < h - 16; ++y)
        for (int x = 16; x < w - 16; ++x)
            PutInstrumentPixel(inst.pixels, w, h, x, y, 40, 44, 52, 90);
    const int cell = 18;
    const int tw = GlyphWordWidth(cell, 5);
    DrawGlyphWord(inst.pixels, w, h, (w - tw) / 2, (h - cell * 7) / 2, cell, "IMAGE", 200, 205, 215, 220);
}

bool PushScaledFrame(Instrument &inst, const uint8_t *src, int sw, int sh, int delayMs) {
    int dw = 0, dh = 0;
    ImageTargetSize(sw, sh, &dw, &dh);
    ImageFrame frame;
    // Floor ~10 fps — faster GIFs just burn SetOverlayRaw and flicker like Media did.
    frame.delayMs = std::max(50, delayMs > 0 ? delayMs : 100);
    frame.rgba.assign(size_t(dw) * dh * 4, 0);
    if (dw == sw && dh == sh)
        std::memcpy(frame.rgba.data(), src, size_t(dw) * dh * 4);
    else
        ScaleRgbaNearest(src, sw, sh, frame.rgba.data(), dw, dh);
    if (inst.imageFrames.empty()) {
        inst.texW = dw;
        inst.texH = dh;
    } else if (dw != inst.texW || dh != inst.texH) {
        std::vector<uint8_t> fitted(size_t(inst.texW) * inst.texH * 4, 0);
        ScaleRgbaNearest(frame.rgba.data(), dw, dh, fitted.data(), inst.texW, inst.texH);
        frame.rgba.swap(fitted);
    }
    inst.imageFrames.push_back(std::move(frame));
    return true;
}

bool LoadInstrumentImageFile(Instrument &inst, const char *path) {
    if (!path || !*path) return false;
    FILE *f = std::fopen(path, "rb");
    if (!f) {
        std::fprintf(stderr, "instrument image: cannot open %s\n", path);
        return false;
    }
    if (std::fseek(f, 0, SEEK_END) != 0) {
        std::fclose(f);
        return false;
    }
    const long sz = std::ftell(f);
    if (sz <= 0 || sz > 16 * 1024 * 1024) {
        std::fclose(f);
        std::fprintf(stderr, "instrument image: bad size %ld for %s\n", sz, path);
        return false;
    }
    if (std::fseek(f, 0, SEEK_SET) != 0) {
        std::fclose(f);
        return false;
    }
    std::vector<uint8_t> buf(static_cast<size_t>(sz));
    if (std::fread(buf.data(), 1, static_cast<size_t>(sz), f) != static_cast<size_t>(sz)) {
        std::fclose(f);
        std::fprintf(stderr, "instrument image: short read %s\n", path);
        return false;
    }
    std::fclose(f);

    // Keep prior frames until the new decode succeeds — a failed replace must not blank VR.
    std::vector<ImageFrame> prevFrames = std::move(inst.imageFrames);
    const int prevW = inst.texW, prevH = inst.texH;
    ClearImageFrames(inst);
    inst.imagePath = path;

    const bool looksGif = (sz >= 6 && buf[0] == 'G' && buf[1] == 'I' && buf[2] == 'F') ||
                          (std::strstr(path, ".gif") != nullptr || std::strstr(path, ".GIF") != nullptr);
    if (looksGif) {
        int *delays = nullptr;
        int w = 0, h = 0, frames = 0, comp = 0;
        stbi_uc *data = stbi_load_gif_from_memory(buf.data(), int(sz), &delays, &w, &h, &frames, &comp, 4);
        if (data && frames > 0 && w > 0 && h > 0) {
            const size_t decoded = size_t(frames) * size_t(w) * size_t(h) * 4ull;
            if (decoded > kImageMaxDecodedBytes) {
                std::fprintf(stderr,
                             "instrument image: GIF too large (%dx%d x %d frames, %llu MB); refusing %s\n", w, h,
                             frames, (unsigned long long)(decoded / (1024ull * 1024ull)), path);
                stbi_image_free(data);
                if (delays) STBI_FREE(delays);
                inst.imageFrames = std::move(prevFrames);
                inst.texW = prevW;
                inst.texH = prevH;
                return false;
            }
            const int n = std::min(frames, kImageMaxFrames);
            const size_t frameBytes = size_t(w) * h * 4;
            for (int i = 0; i < n; ++i) {
                const int delay = delays ? delays[i] : 100;
                PushScaledFrame(inst, data + frameBytes * size_t(i), w, h, delay);
            }
            stbi_image_free(data);
            if (delays) STBI_FREE(delays);
            if (!inst.imageFrames.empty()) return true;
        }
        if (data) stbi_image_free(data);
        if (delays) STBI_FREE(delays);
    }

    int w = 0, h = 0, comp = 0;
    stbi_uc *data = stbi_load_from_memory(buf.data(), int(sz), &w, &h, &comp, 4);
    if (!data || w <= 0 || h <= 0) {
        std::fprintf(stderr, "instrument image: decode failed %s (%s)\n", path, stbi_failure_reason());
        if (data) stbi_image_free(data);
        inst.imageFrames = std::move(prevFrames);
        inst.texW = prevW;
        inst.texH = prevH;
        return false;
    }
    const size_t decoded = size_t(w) * size_t(h) * 4ull;
    if (decoded > kImageMaxDecodedBytes) {
        std::fprintf(stderr, "instrument image: still too large (%dx%d); refusing %s\n", w, h, path);
        stbi_image_free(data);
        inst.imageFrames = std::move(prevFrames);
        inst.texW = prevW;
        inst.texH = prevH;
        return false;
    }
    PushScaledFrame(inst, data, w, h, 0);
    stbi_image_free(data);
    if (inst.imageFrames.empty()) {
        inst.imageFrames = std::move(prevFrames);
        inst.texW = prevW;
        inst.texH = prevH;
        return false;
    }
    return true;
}

void UploadImageOverlay(Instrument &inst, bool chrome) {
    if (inst.overlay == vr::k_ulOverlayHandleInvalid) return;
    const size_t need = size_t(inst.texW) * size_t(inst.texH) * 4ull;
    if (inst.pixels.size() != need || inst.texW <= 0 || inst.texH <= 0) {
        std::fprintf(stderr, "instrument image: refusing SetOverlayRaw size mismatch %zu vs %dx%d\n",
                     inst.pixels.size(), inst.texW, inst.texH);
        return;
    }
    vr::VROverlay()->SetOverlayRaw(inst.overlay, inst.pixels.data(), uint32_t(inst.texW),
                                   uint32_t(inst.texH), 4);
    if (chrome) {
        vr::VROverlay()->SetOverlayWidthInMeters(inst.overlay, float(inst.metres));
        PlaceInstrumentChrome(inst);
    }
}

void RefreshImageTexture(Instrument &inst, bool force) {
    if (inst.type != InstrumentType::Image) return;
    if (inst.imageFrames.empty()) {
        if (!force && !inst.pixels.empty() && inst.lastImageFrame == -2) return;
        DrawImagePlaceholder(inst);
        inst.lastImageFrame = -2;
        UploadImageOverlay(inst, true);
        return;
    }
    if (inst.imageFrame < 0 || inst.imageFrame >= int(inst.imageFrames.size())) inst.imageFrame = 0;
    if (!force && inst.imageFrame == inst.lastImageFrame && !inst.pixels.empty()) return;
    const ImageFrame &frame = inst.imageFrames[size_t(inst.imageFrame)];
    const size_t need = size_t(inst.texW) * size_t(inst.texH) * 4ull;
    if (frame.rgba.size() != need) {
        std::fprintf(stderr, "instrument image: frame size mismatch; skipping upload\n");
        return;
    }
    // Avoid copying the whole frame vector every tick — swap pointers via assign only when needed.
    inst.pixels = frame.rgba;
    const bool sizeChanged = inst.lastImageFrame < 0;
    inst.lastImageFrame = inst.imageFrame;
    // Chrome only when size/pose-relevant state may have changed — every-frame PlaceInstrumentChrome
    // flickered the same way Media's SoftOutline did.
    UploadImageOverlay(inst, sizeChanged || force);
}

void TickImageAnimation(Instrument &inst, double dt) {
    if (inst.type != InstrumentType::Image || inst.imageFrames.size() < 2) return;
    inst.imageFrameAccMs += dt * 1000.0;
    if (inst.imageFrame < 0 || inst.imageFrame >= int(inst.imageFrames.size())) inst.imageFrame = 0;
    const int delay = std::max(50, inst.imageFrames[size_t(inst.imageFrame)].delayMs);
    if (inst.imageFrameAccMs < delay) return;
    // Advance one frame per tick max — the old catch-up loop uploaded up to 8 frames/tick.
    inst.imageFrameAccMs = std::fmod(inst.imageFrameAccMs, double(delay));
    inst.imageFrame = (inst.imageFrame + 1) % int(inst.imageFrames.size());
    RefreshImageTexture(inst, false);
}

bool SetInstrumentImagePath(Instrument &inst, const char *path) {
    if (inst.type != InstrumentType::Image && inst.type != InstrumentType::Launcher) return false;
    if (!LoadInstrumentImageFile(inst, path)) {
        // Keep whatever was on screen; show placeholder only if we have nothing.
        // Do not mutate launchAppear — a failed load must not permanently force "fallback"
        // (that would ignore a later successful file push while appear stayed wrong).
        if (inst.type == InstrumentType::Image && inst.imageFrames.empty()) RefreshImageTexture(inst, true);
        if (inst.type == InstrumentType::Launcher && inst.imageFrames.empty()) RefreshLauncherTexture(inst, true);
        return false;
    }
    inst.imagePath = path ? path : "";
    if (inst.type == InstrumentType::Launcher) {
        inst.lastLauncherKey = -1;
        RefreshLauncherTexture(inst, true);
        PlaceInstrumentChrome(inst);
        return true;
    }
    RefreshImageTexture(inst, true);
    PlaceInstrumentChrome(inst);
    return true;
}

void RefreshInstrumentContent(Instrument &inst, bool force) {
    switch (inst.type) {
        case InstrumentType::Clock: RefreshClockTexture(inst, force); break;
        case InstrumentType::Battery: RefreshBatteryTexture(inst, force); break;
        case InstrumentType::Storage:
        case InstrumentType::Sd: RefreshStorageTexture(inst, force); break;
        case InstrumentType::Date: RefreshDateTexture(inst, force); break;
        case InstrumentType::Media: RefreshMediaTexture(inst, force); break;
        case InstrumentType::Image: RefreshImageTexture(inst, force); break;
        case InstrumentType::Launcher: RefreshLauncherTexture(inst, force); break;
    }
}

void DestroyInstrumentOverlays(Instrument &inst) {
    if (inst.overlay != vr::k_ulOverlayHandleInvalid) {
        vr::VROverlay()->DestroyOverlay(inst.overlay);
        inst.overlay = vr::k_ulOverlayHandleInvalid;
    }
    if (inst.bar != vr::k_ulOverlayHandleInvalid) {
        vr::VROverlay()->DestroyOverlay(inst.bar);
        inst.bar = vr::k_ulOverlayHandleInvalid;
    }
    inst.visible = false;
    inst.controls = 0;
    inst.controlsUp = false;
    inst.barLit = false;
    inst.hoverBar = false;
}

void EnsureInstrumentOverlays(Instrument &inst) {
    if (inst.overlay != vr::k_ulOverlayHandleInvalid) return;
    char key[64], name[64];
    std::snprintf(key, sizeof key, "frametop.instrument.%s", inst.id.c_str());
    std::snprintf(name, sizeof name, "Instrument %s", inst.id.c_str());
    inst.overlay = CreateOrRecycleOverlay(key, name);
    if (inst.overlay == vr::k_ulOverlayHandleInvalid) {
        std::fprintf(stderr, "openvr: can't create instrument overlay %s\n", key);
        return;
    }
    vr::VROverlay()->SetOverlayWidthInMeters(inst.overlay, float(inst.metres));
    vr::VROverlay()->SetOverlaySortOrder(inst.overlay, 0);
    if (inst.type == InstrumentType::Media || inst.type == InstrumentType::Launcher) {
        // Media transport / Launcher icon need laser clicks on the content overlay.
        vr::VROverlay()->SetOverlayInputMethod(inst.overlay, vr::VROverlayInputMethod_Mouse);
        vr::VROverlay()->SetOverlayFlag(inst.overlay, vr::VROverlayFlags_MakeOverlaysInteractiveIfVisible, true);
        vr::HmdVector2_t scale = {(float)inst.texW, (float)inst.texH};
        vr::VROverlay()->SetOverlayMouseScale(inst.overlay, &scale);
    } else {
        vr::VROverlay()->SetOverlayInputMethod(inst.overlay, vr::VROverlayInputMethod_None);
    }
    std::snprintf(key, sizeof key, "frametop.instrument.%s.bar", inst.id.c_str());
    std::snprintf(name, sizeof name, "Instrument %s: move", inst.id.c_str());
    inst.bar = MakeChrome(key, name, BarTexture(false), 256, 24);
    if (inst.bar != vr::k_ulOverlayHandleInvalid) {
        vr::VROverlay()->SetOverlayFlag(inst.bar, vr::VROverlayFlags_MakeOverlaysInteractiveIfVisible, true);
        vr::VROverlay()->SetOverlayFlag(inst.bar, vr::VROverlayFlags_SendVRDiscreteScrollEvents, true);
    }
    inst.attentionResolved = inst.activeOpacity;
    RefreshInstrumentContent(inst, true);
    ApplyInstrumentAlpha(inst);
}

void ShowInstrument(Instrument &inst, bool on) {
    if (!on) {
        if (inst.visible) {
            if (inst.overlay != vr::k_ulOverlayHandleInvalid) vr::VROverlay()->HideOverlay(inst.overlay);
            if (inst.bar != vr::k_ulOverlayHandleInvalid) vr::VROverlay()->HideOverlay(inst.bar);
            inst.visible = false;
            inst.controls = 0;
            inst.controlsUp = false;
        }
        return;
    }
    EnsureInstrumentOverlays(inst);
    if (inst.overlay == vr::k_ulOverlayHandleInvalid) return;
    if (!inst.visible) {
        vr::VROverlay()->ShowOverlay(inst.overlay);
        inst.visible = true;
    }
    // Keep the move bar shown (transparent until proximity) so lasers can hit it — same
    // policy as screen chrome. Hiding it until proximity made discovery nearly impossible.
    if (inst.bar != vr::k_ulOverlayHandleInvalid && !inst.controlsUp) {
        vr::VROverlay()->SetOverlayInputMethod(inst.bar, vr::VROverlayInputMethod_Mouse);
        vr::VROverlay()->ShowOverlay(inst.bar);
        inst.controlsUp = true;
    }
    ApplyInstrumentAlpha(inst);
}

void RecenterInstrument(Instrument &inst) {
    SetInstrumentAbsolute(inst, DefaultInstrumentPose());
}

void EndInstrumentDrag(Instrument &inst) {
    inst.drag = Drag::None;
    inst.dragDevice = kNone;
    LightInstrumentBar(inst, false);
    ApplyInstrumentAlpha(inst);
}

void FinishInstrumentDrag(Instrument &inst) {
    const bool moved = inst.drag == Drag::Move;
    const AnchorMode restore = inst.dragRestore;
    EndInstrumentDrag(inst);
    inst.dragRestore = AnchorMode::World;
    if (!moved) return;
    Mat p;
    if (IsSoftFollow(restore) && InstrumentPose(inst, &p)) {
        Mat hmd;
        if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &hmd)) return;
        SetInstrumentFollow(inst, restore, Mul(Inverse(ReferenceFrame(restore, hmd)), p));
    }
}

void EndInstrumentDragsBy(vr::TrackedDeviceIndex_t dev) {
    for (auto &inst : g_instruments)
        if (inst.drag != Drag::None && inst.dragDevice == dev) FinishInstrumentDrag(inst);
}

void StartInstrumentDrag(Instrument &inst, vr::TrackedDeviceIndex_t dev) {
    Mat d, p;
    if (dev == kNone || !DevicePose(dev, &d) || !InstrumentPose(inst, &p)) return;
    inst.dragRestore = inst.anchor;
    if (inst.pinned != kNone) {
        inst.pinned = kNone;
        inst.pose = p;
        if (inst.overlay != vr::k_ulOverlayHandleInvalid)
            vr::VROverlay()->SetOverlayTransformAbsolute(inst.overlay, vr::TrackingUniverseStanding, &p);
        PlaceInstrumentChrome(inst);
    }
    inst.drag = Drag::Move;
    inst.dragDevice = dev;
    inst.dragRel = Mul(Inverse(d), p);
    LightInstrumentBar(inst, false);
    ApplyInstrumentAlpha(inst);
}

void UpdateInstrumentDrag(Instrument &inst) {
    Mat d;
    if (inst.drag != Drag::Move || !DevicePose(inst.dragDevice, &d)) return;
    SetInstrumentAbsolute(inst, Mul(d, inst.dragRel));
}

void PushInstrument(Instrument &inst, double notches) {
    Mat d, head;
    if (!DevicePose(inst.dragDevice, &d) || !DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head)) return;
    Mat p = Mul(d, inst.dragRel);
    const double to[3] = {p.m[0][3] - head.m[0][3], p.m[1][3] - head.m[1][3], p.m[2][3] - head.m[2][3]};
    const double len = std::sqrt(Dot3(to, to));
    const double next = std::clamp(len * (1 + 0.08 * notches), 0.3, 10.0);
    for (int k = 0; k < 3; ++k) p.m[k][3] = float(head.m[k][3] + to[k] / (len + 1e-9) * next);
    inst.dragRel = Mul(Inverse(d), p);
}

void UpdateInstrumentAttention(double dt) {
    for (size_t ii = 0; ii < g_instruments.size(); ++ii) {
        Instrument &inst = g_instruments[ii];
        if (!inst.enabled) continue;
        const float before = inst.attentionResolved;
        if (!inst.attentionEnabled) {
            inst.attentionFocused = false;
            inst.attentionFocusMs = 0;
            inst.attentionResolved = inst.activeOpacity;
        } else if (!g_eyeAvailable && !g_gazeFallbackHead) {
            inst.attentionFocused = false;
            inst.attentionFocusMs = 0;
            inst.attentionResolved = inst.activeOpacity;
        } else {
            const bool hit = g_gazeTarget && g_gazeTarget.instrument == int(ii) &&
                             g_gazeTarget.kind == GazeKind::Instrument;
            const bool valid = g_eyeValid || g_eyeHeld || (g_gazeFallbackHead && g_gazeTarget);
            if (!valid) {
                if (inst.attentionFocused) {
                    inst.attentionFocusMs += dt * 1000.0;
                    if (inst.attentionFocusMs >= inst.attentionHoldMs) {
                        inst.attentionFocused = false;
                        inst.attentionFocusMs = 0;
                    }
                }
                const float target = inst.attentionFocused ? inst.activeOpacity : inst.idleOpacity;
                const double tauMs = inst.attentionFocused ? inst.attentionInMs : inst.attentionOutMs;
                const double tau = tauMs / 1000.0;
                const double a = tau <= 1e-4 ? 1.0 : 1.0 - std::exp(-dt / tau);
                inst.attentionResolved =
                    float(inst.attentionResolved + (target - inst.attentionResolved) * a);
            } else {
                if (hit) {
                    inst.attentionFocusMs += dt * 1000.0;
                    if (!inst.attentionFocused && inst.attentionFocusMs >= inst.attentionDwellMs)
                        inst.attentionFocused = true;
                } else if (inst.attentionFocused) {
                    inst.attentionFocusMs += dt * 1000.0;
                    if (inst.attentionFocusMs >= inst.attentionHoldMs) {
                        inst.attentionFocused = false;
                        inst.attentionFocusMs = 0;
                    }
                } else {
                    inst.attentionFocusMs = 0;
                }
                if (hit && inst.attentionFocused) inst.attentionFocusMs = 0;
                const float target = inst.attentionFocused ? inst.activeOpacity : inst.idleOpacity;
                const double tauMs = inst.attentionFocused ? inst.attentionInMs : inst.attentionOutMs;
                const double tau = tauMs / 1000.0;
                const double a = tau <= 1e-4 ? 1.0 : 1.0 - std::exp(-dt / tau);
                inst.attentionResolved = float(inst.attentionResolved + (target - inst.attentionResolved) * a);
            }
        }
        if (std::fabs(inst.attentionResolved - before) > 0.001f) ApplyInstrumentAlpha(inst);
    }
}

void UpdateInstrumentControls() {
    std::vector<Mat> lasers;
    for (vr::TrackedDeviceIndex_t i = 1; i < vr::k_unMaxTrackedDeviceCount; ++i) {
        Mat d;
        if (vr::VRSystem()->GetTrackedDeviceClass(i) == vr::TrackedDeviceClass_Controller && LaserPose(i, &d))
            lasers.push_back(d);
    }
    for (auto &inst : g_instruments) {
        if (!inst.enabled || !inst.visible) continue;
        Mat p;
        if (InstrumentPose(inst, &p)) {
            const double chrome = std::max(0.04, inst.metres * 0.18);
            const double hw = inst.metres * 0.5, hh = inst.heightMetres() * 0.5;
            // Reach covers the face + bar (screen chrome uses ~grip*1.5); old reach ~3 cm
            // only sampled the bar and was nearly unusable.
            const double reach = std::max({inst.metres * 0.14, chrome * 0.85, 0.07});
            std::vector<Mat> spots;
            const Mat bar = Mul(p, InstrumentBarOffset(inst));
            for (double f : {-0.5, -0.25, 0.0, 0.25, 0.5})
                spots.push_back(Mul(bar, Translation(f * chrome, 0, 0)));
            // Face samples so aiming at the instrument itself reveals the move bar.
            for (double fx : {-0.45, 0.0, 0.45})
                for (double fy : {-0.35, 0.0, 0.35})
                    spots.push_back(Mul(p, Translation(fx * hw * 2, fy * hh * 2, 0)));
            for (const Mat &d : lasers) {
                const double o[3] = {d.m[0][3], d.m[1][3], d.m[2][3]}, dir[3] = {-d.m[0][2], -d.m[1][2], -d.m[2][2]};
                bool close = false;
                for (const Mat &c : spots) {
                    const double v[3] = {c.m[0][3] - o[0], c.m[1][3] - o[1], c.m[2][3] - o[2]};
                    const double t = Dot3(v, dir);
                    if (t <= 0) continue;
                    const double q[3] = {v[0] - dir[0] * t, v[1] - dir[1] * t, v[2] - dir[2] * t};
                    if (Dot3(q, q) <= reach * reach) {
                        close = true;
                        break;
                    }
                }
                if (close) {
                    inst.nearUntil = g_tick + kControlsLinger;
                    break;
                }
            }
        }
        const bool inUse = inst.drag != Drag::None || inst.hoverBar;
        const bool want = inst.visible && (inUse || g_tick < inst.nearUntil);
        // Bar stays shown while visible (transparent); only fade controls brightness.
        if (inst.bar != vr::k_ulOverlayHandleInvalid && !inst.controlsUp) {
            vr::VROverlay()->SetOverlayInputMethod(inst.bar, vr::VROverlayInputMethod_Mouse);
            vr::VROverlay()->ShowOverlay(inst.bar);
            inst.controlsUp = true;
        }
        const float before = inst.controls;
        inst.controls = std::clamp(inst.controls + (want ? 0.2f : -0.1f), 0.f, 1.f);
        if (inst.controls != before) ApplyInstrumentAlpha(inst);
    }
}

void PollInstrumentBars() {
    for (auto &inst : g_instruments) {
        if (!inst.enabled || inst.bar == vr::k_ulOverlayHandleInvalid) continue;
        vr::VREvent_t ev;
        while (vr::VROverlay()->PollNextOverlayEvent(inst.bar, &ev, sizeof ev)) {
            const bool on = ev.eventType == vr::VREvent_MouseMove || ev.eventType == vr::VREvent_FocusEnter;
            if (on || ev.eventType == vr::VREvent_FocusLeave) {
                if (inst.hoverBar != on) {
                    inst.hoverBar = on;
                    ApplyInstrumentAlpha(inst);
                }
            }
            if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                StartInstrumentDrag(inst, ev.trackedDeviceIndex);
            else if (ev.eventType == vr::VREvent_MouseButtonUp) {
                EndInstrumentDragsBy(ev.trackedDeviceIndex);
                EndDragsBy(ev.trackedDeviceIndex);
            } else if (ev.eventType == vr::VREvent_ScrollDiscrete && inst.drag == Drag::Move)
                PushInstrument(inst, ev.data.scroll.ydelta);
        }
        if (inst.drag != Drag::None) UpdateInstrumentDrag(inst);
    }
}

void SetInstrumentWidth(Instrument &inst, double metres) {
    inst.metres = std::clamp(metres, 0.08, 2.0);
    if (inst.overlay != vr::k_ulOverlayHandleInvalid)
        vr::VROverlay()->SetOverlayWidthInMeters(inst.overlay, float(inst.metres));
    PlaceInstrumentChrome(inst);
}

void SetInstrumentOpacity(Instrument &inst, float active, float idle) {
    inst.activeOpacity = std::clamp(active, 0.f, 1.f);
    inst.idleOpacity = std::clamp(idle, 0.f, 1.f);
    if (inst.idleOpacity > inst.activeOpacity) std::swap(inst.idleOpacity, inst.activeOpacity);
    if (!inst.attentionEnabled || (!g_eyeAvailable && !g_gazeFallbackHead))
        inst.attentionResolved = inst.activeOpacity;
    else
        inst.attentionResolved = std::clamp(inst.attentionResolved, std::min(inst.idleOpacity, inst.activeOpacity),
                                            std::max(inst.idleOpacity, inst.activeOpacity));
    ApplyInstrumentAlpha(inst);
}

bool ParseInstrumentColor(const char *hex, uint8_t *r, uint8_t *g, uint8_t *b) {
    if (!hex || !r || !g || !b) return false;
    if (hex[0] == '#') ++hex;
    unsigned v = 0;
    if (std::strlen(hex) != 6) return false;
    for (int i = 0; i < 6; ++i) {
        const char c = hex[i];
        v <<= 4;
        if (c >= '0' && c <= '9') v |= unsigned(c - '0');
        else if (c >= 'a' && c <= 'f') v |= unsigned(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F') v |= unsigned(c - 'A' + 10);
        else return false;
    }
    *r = uint8_t((v >> 16) & 0xFF);
    *g = uint8_t((v >> 8) & 0xFF);
    *b = uint8_t(v & 0xFF);
    return true;
}

void SetInstrumentColor(Instrument &inst, uint8_t r, uint8_t g, uint8_t b) {
    inst.colorR = r;
    inst.colorG = g;
    inst.colorB = b;
    // Bust content caches so the next refresh repaints with the new colour.
    inst.lastMinute = -1;
    inst.lastDateKey = -1;
    inst.lastBatterySeg = -1;
    inst.lastMediaKey = -1;
    RefreshInstrumentContent(inst, true);
}

void EnableInstrument(Instrument &inst, bool on) {
    if (on) {
        EnsureInstrumentOverlays(inst);
        if (IsIdentityMat(inst.pose) && inst.pinned == kNone) RecenterInstrument(inst);
        else if (inst.overlay != vr::k_ulOverlayHandleInvalid) {
            if (inst.pinned != kNone)
                vr::VROverlay()->SetOverlayTransformTrackedDeviceRelative(inst.overlay, inst.pinned, &inst.pinRel);
            else
                vr::VROverlay()->SetOverlayTransformAbsolute(inst.overlay, vr::TrackingUniverseStanding, &inst.pose);
            PlaceInstrumentChrome(inst);
        }
        inst.enabled = true;
        ShowInstrument(inst, true);
    } else {
        EndInstrumentDrag(inst);
        ShowInstrument(inst, false);
        DestroyInstrumentOverlays(inst);
        inst.enabled = false;
    }
}

void ClearInstruments() {
    for (auto &inst : g_instruments) {
        EndInstrumentDrag(inst);
        DestroyInstrumentOverlays(inst);
        inst.enabled = false;
    }
    g_instruments.clear();
}

const char *InstrumentTypeName(InstrumentType t) {
    switch (t) {
        case InstrumentType::Clock: return "clock";
        case InstrumentType::Battery: return "battery";
        case InstrumentType::Storage: return "storage";
        case InstrumentType::Sd: return "sd";
        case InstrumentType::Date: return "date";
        case InstrumentType::Media: return "media";
        case InstrumentType::Image: return "image";
        case InstrumentType::Launcher: return "launcher";
    }
    return "clock";
}

void TickInstruments(double dt) {
    UpdateInstrumentVisibility();
    for (auto &inst : g_instruments) {
        if (!inst.enabled) continue;
        RefreshInstrumentContent(inst, false);
        if (inst.type == InstrumentType::Media) PollMediaOverlay(inst);
        if (inst.type == InstrumentType::Launcher) PollLauncherOverlay(inst);
        if (inst.type == InstrumentType::Image) TickImageAnimation(inst, dt);
    }
    UpdateInstrumentFollow(dt);
    UpdateInstrumentControls();
    PollInstrumentBars();
}

// Same shared ModeVisible / wrist rules as screens: hide with the displays during a VR
// game (unless ingames visible, or the dashboard / hide hotkey brings them back), and
// keep a mid-drag instrument up so a grab is not cancelled by a mode change.
void UpdateInstrumentVisibility() {
    const bool shared = ModeVisible();
    const bool dash = vr::VROverlay()->IsDashboardVisible();
    const bool yield = DashboardYieldActive();
    Mat head;
    const bool haveHead = DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head);
    for (size_t ii = 0; ii < g_instruments.size(); ++ii) {
        Instrument &inst = g_instruments[ii];
        ApplyOverlaySort(inst.overlay, 0, dash);
        ApplyOverlaySort(inst.bar, dash ? 0 : 1, dash);
        if (!inst.enabled) {
            ShowInstrument(inst, false);
            continue;
        }
        bool visible = shared || inst.drag != Drag::None;
        float visFade = 1.f;
        Mat p;
        if (visible && inst.pinned != kNone && IsHandController(inst.pinned) && inst.drag == Drag::None &&
            haveHead && InstrumentPose(inst, &p)) {
            const double a = FacingAngle(p, head);
            visFade = float(std::clamp((g_wristAngle - a) / kFade, 0.0, 1.0));
            visible = visFade > 0.02f;
        }
        if (!visible && shared && inst.controls > 0.02f) visible = true, visFade = 0.f;
        if (yield && visible && !InstrumentKeepsThroughDashboard(ii, inst)) {
            visible = false;
            visFade = 0.f;
        }
        inst.visibilityFade = visFade;
        ShowInstrument(inst, visible);
    }
}

#include "desktop_toolbar.inc"

// Steam in front: the dashboard (the Steam menu) is open, or Steam's own keyboard is up
// (valve.steam.gamepadui.keyboard, for text fields in Steam and the dashboard). Our
// keyboard steps aside then, and comes back where it was when Steam is out of the way; one
// asked for meanwhile appears then. Checked every 9 ticks; Steam makes its keyboard's
// overlay again now and then, so it's looked up each time.
bool g_steamInFront = false;
bool g_keyboardAside = false;   // ours is waiting for Steam to get out of the way
Mat g_asidePose = Identity();   // ...and goes here then

bool SteamInFront() {
    vr::VROverlayHandle_t h = vr::k_ulOverlayHandleInvalid;
    // In the dashboard mode the screens only show with the dashboard, so it doesn't count.
    return (g_mode != Mode::Dashboard && vr::VROverlay()->IsDashboardVisible()) ||
           (vr::VROverlay()->FindOverlay("valve.steam.gamepadui.keyboard", &h) == vr::VROverlayError_None &&
            vr::VROverlay()->IsOverlayVisible(h));
}

void UpdateSteamInFront() {
    const bool front = SteamInFront();
    if (front == g_steamInFront) return;
    g_steamInFront = front;
    if (front && keyboard::Shown()) {
        g_asidePose = keyboard::Pose();
        keyboard::Hide();
        g_keyboardAside = true;
    } else if (!front && g_keyboardAside) {
        g_keyboardAside = false;
        keyboard::Show(g_asidePose);
    }
}

}  // namespace

extern "C" {

bool ft_vr_init(void) {
    vr::EVRInitError err = vr::VRInitError_None;
    // Background first: Overlay VR_Init starts vrserver itself when none is running,
    // and a rogue one (e.g. from the container) never finds the HMD.
    vr::VR_Init(&err, vr::VRApplication_Background);
    if (err == vr::VRInitError_None) {
        vr::VR_Shutdown();
        err = vr::VRInitError_None;
        vr::VR_Init(&err, vr::VRApplication_Overlay);
    }
    if (err != vr::VRInitError_None) {
        std::fprintf(stderr, "openvr: %s\n", vr::VR_GetVRInitErrorAsEnglishDescription(err));
        return false;
    }
    if (!vr::VRIPCResourceManager()) {
        std::fprintf(stderr, "openvr: no IVRIPCResourceManagerClient (SteamVR too old?)\n");
        return false;
    }
    // Action manifest must be set before the first PollNextEvent / UpdateActionState.
    InitEyeTracking();
    RefreshPoses();
    g_vr = true;
    SeedDesktopgameOverlays();
    // The catcher: clear and invisible, but the laser lands on it for off-panel releases.
    if (vr::VROverlay()->CreateOverlay("frametop.catcher", "Frametop: release catcher", &g_catcher) ==
        vr::VROverlayError_None) {
        static std::vector<uint8_t> clear(4 * 4 * 4, 0);
        vr::VROverlay()->SetOverlayRaw(g_catcher, clear.data(), 4, 4, 4);
        vr::VROverlay()->SetOverlayInputMethod(g_catcher, vr::VROverlayInputMethod_Mouse);
        vr::VROverlay()->SetOverlayAlpha(g_catcher, 0);
        vr::VROverlay()->SetOverlayFlag(g_catcher, vr::VROverlayFlags_MakeOverlaysInteractiveIfVisible, true);
    }
    return true;
}

void ft_vr_shutdown(void) {
    if (!g_vr) return;
    // Best-effort teardown: after a dying SteamVR, overlay calls may fail; still attempt
    // VR_Shutdown so we do not strand the runtime when SIGTERM reaches us in time.
    try {
        ClearInstruments();
        if (g_catcher != vr::k_ulOverlayHandleInvalid) vr::VROverlay()->DestroyOverlay(g_catcher);
        g_catcher = vr::k_ulOverlayHandleInvalid;
        for (auto &[i, s] : g_screens) {
            for (auto &[k, sub] : s.subs)
                if (sub.overlay != vr::k_ulOverlayHandleInvalid) vr::VROverlay()->DestroyOverlay(sub.overlay);
            for (auto o : s.All()) {
                if (o != vr::k_ulOverlayHandleInvalid)
                    vr::VROverlay()->DestroyOverlay(o);
            }
        }
        for (auto &[dev, g] : g_guides)
            for (auto o : {g.ring.overlay, g.dot.overlay}) {
                if (o != vr::k_ulOverlayHandleInvalid)
                    vr::VROverlay()->DestroyOverlay(o);
            }
        if (auto *ipc = vr::VRIPCResourceManager()) {
            for (auto &[k, h] : g_imports) ipc->UnrefResource(h);
            for (auto &[k, h] : g_cutImports) ipc->UnrefResource(h);
        }
        g_cutImports.clear();
        keyboard::Destroy();
    } catch (...) {
        std::fprintf(stderr, "ft_vr_shutdown: overlay cleanup failed; still shutting down OpenVR\n");
    }
    g_guides.clear();
    g_screens.clear();
    g_imports.clear();
    vr::VR_Shutdown();
    g_vr = false;
}

int ft_vr_modifiers(uint32_t format, uint64_t *out, int max) {
    if (!g_vr) {  // --no-vr: nothing imports the buffers, so any layout KWin can draw
        if (max < 1) return 0;
        out[0] = 0;  // DRM_FORMAT_MOD_LINEAR
        return 1;
    }
    uint32_t n = uint32_t(max);
    if (!vr::VRIPCResourceManager()->GetDmabufModifiers(vr::VRApplication_Overlay, format, &n, out)) return 0;
    return int(n < uint32_t(max) ? n : uint32_t(max));
}

bool ft_vr_screens_shown(void) { return g_vr && ModeVisible(); }

}  // extern "C"

namespace {

// A panel and its controls. `prefix` names the overlays (frametop.screen.N / frametop.float.N).
bool MakePanel(Screen &s, const char *prefix, const char *label) {
    char key[64], name[64];
    std::snprintf(key, sizeof key, "%s", prefix);
    std::snprintf(name, sizeof name, "%s", label);
    s.overlay = CreateOrRecycleOverlay(key, name);
    if (s.overlay == vr::k_ulOverlayHandleInvalid) {
        std::fprintf(stderr, "openvr: can't create overlay %s\n", key);
        return false;
    }
    // Profile digits used to live under every screen; Displays owns them now. Purge any
    // leftover keys from a hard-killed older binary so they cannot reappear mid-session.
    for (int i = 1; i <= kSlotCount; ++i) {
        char slotKey[80];
        std::snprintf(slotKey, sizeof slotKey, "%s.slot%d", prefix, i);
        vr::VROverlayHandle_t leftover = vr::k_ulOverlayHandleInvalid;
        if (vr::VROverlay()->FindOverlay(slotKey, &leftover) == vr::VROverlayError_None)
            vr::VROverlay()->DestroyOverlay(leftover);
    }
    vr::VROverlay()->SetOverlayWidthInMeters(s.overlay, float(s.metres));
    vr::VROverlay()->SetOverlayInputMethod(s.overlay, vr::VROverlayInputMethod_Mouse);
    vr::VROverlay()->SetOverlaySortOrder(s.overlay, 0);
    vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_IgnoreTextureAlpha, true);
    vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_SendVRDiscreteScrollEvents, true);
    vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_MakeOverlaysInteractiveIfVisible, true);
    // Floating spares: only the main panel here. EnsureFloatChrome adds bar/dock/close when used.
    if (s.floating) {
        s.attentionResolved = s.activeOpacity;
        ApplyAlpha(s);
        return true;
    }
    static const auto corner = CornerTexture(64);
    static const auto curve = CurveTexture(64);
    static const auto roll = RollTexture(64);
    auto chrome = [&](const char *part, const char *what, const std::vector<uint8_t> &px, int w, int h) {
        std::snprintf(key, sizeof key, "%s.%s", prefix, part);
        std::snprintf(name, sizeof name, "%s: %s", label, what);
        return MakeChrome(key, name, px, w, h);
    };
    s.bar = chrome("bar", "move", BarTexture(false), 256, 24);
    vr::VROverlay()->SetOverlayFlag(s.bar, vr::VROverlayFlags_SendVRDiscreteScrollEvents, true);
    s.curveButton = chrome("curve", "curve", curve, 64, 64);
    s.rollButton = chrome("roll", "roll", roll, 64, 64);
    vr::VROverlay()->SetOverlayFlag(s.rollButton, vr::VROverlayFlags_SendVRDiscreteScrollEvents, true);
    s.handle = chrome("resize", "resize", corner, 64, 64);
    s.anchorButton = chrome("anchor", "anchor", AnchorTexture(64, AnchorMode::World), 64, 64);
    s.dockButton = chrome("dock", "dock to toolbar", DockTexture(64, false), 64, 64);
    s.attentionResolved = s.activeOpacity;
    PlaceChrome(s);  // sizes dock to grip (OpenVR default width is huge without this)
    ApplyAlpha(s);
    return true;
}

}  // namespace

extern "C" {

void ft_vr_screen_create(int index, double metres, int count) {
    if (!g_vr) return;
    Screen &s = g_screens[index];
    s.metres = metres;
    char prefix[64], label[64];
    std::snprintf(prefix, sizeof prefix, "frametop.screen.%d", index + 1);
    std::snprintf(label, sizeof label, "Screen %d", index + 1);
    if (!MakePanel(s, prefix, label)) return;
    // Until the layout places it: 2 m ahead of the head, in a row, screen 1 on the left.
    RefreshPoses();
    Mat head;
    if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head)) head = Identity();
    const double heading = std::atan2(head.m[0][2], head.m[2][2]) * 180 / M_PI;
    const double yaw = heading + (double(count - 1) / 2 - index) * 35;
    const double dx = -std::sin(yaw * M_PI / 180), dz = -std::cos(yaw * M_PI / 180);
    SetAbsolute(s, PanelPose(head.m[0][3] + dx * 2, head.m[1][3], head.m[2][3] + dz * 2, yaw, 0, 0));
}

void ft_vr_float_create(int index, int slot) {
    if (!g_vr) return;
    Screen &s = g_screens[index];
    s.floating = true;
    s.floatSlot = slot;
    s.metres = 0.5;
    char prefix[64], label[64];
    std::snprintf(prefix, sizeof prefix, "frametop.float.%d", slot);
    std::snprintf(label, sizeof label, "Floating window %d", slot);
    MakePanel(s, prefix, label);
}

void ft_vr_float_output(int index, bool on) {
    auto it = g_screens.find(index);
    if (it != g_screens.end()) it->second.outputOn = on;
}

void ft_vr_screen_destroy(int index) {
    auto it = g_screens.find(index);
    if (it == g_screens.end()) return;
    if (g_cutterState == 1) g_cutter.DropPanel(index);
    for (auto &[k, sub] : it->second.subs) vr::VROverlay()->DestroyOverlay(sub.overlay);
    for (auto o : it->second.All())
        if (o != vr::k_ulOverlayHandleInvalid) vr::VROverlay()->DestroyOverlay(o);
    g_screens.erase(it);
}

bool ft_vr_screen_present(int index, const void *key, const struct ft_dmabuf *b) {
    if (!g_vr) return false;
    auto sit = g_screens.find(index);
    if (sit == g_screens.end()) return false;
    Screen &s = sit->second;
    auto it = g_imports.find(key);
    if (it == g_imports.end()) {
        vr::DmabufAttributes_t a{};
        a.unWidth = uint32_t(b->width);
        a.unHeight = uint32_t(b->height);
        a.unDepth = a.unMipLevels = a.unArrayLayers = a.unSampleCount = 1;
        a.unFormat = b->format;
        a.ulModifier = b->modifier;
        a.unPlaneCount = uint32_t(b->n_planes);
        for (int i = 0; i < b->n_planes && i < int(vr::MaxDmabufPlaneCount); ++i) {
            a.plane[i].unOffset = b->offset[i];
            a.plane[i].unStride = b->stride[i];
            a.plane[i].nFd = b->fd[i];
        }
        vr::SharedTextureHandle_t h = 0;
        if (!vr::VRIPCResourceManager()->ImportDmabuf(vr::VRApplication_Overlay, &a, &h)) {
            std::fprintf(stderr, "openvr: ImportDmabuf failed: %dx%d format 0x%x modifier 0x%llx\n", b->width,
                         b->height, b->format, (unsigned long long)b->modifier);
            return false;
        }
        it = g_imports.emplace(key, h).first;
    }
    if (b->width != s.width || b->height != s.height) {
        s.width = b->width, s.height = b->height;
        if (s.floating) {
            ApplyCrop(s);
        } else {
            // Mouse scale stays in *buffer* pixels; seat events map via ft_buffer_to_surface.
            vr::HmdVector2_t scale = {float(s.width), float(s.height)};
            vr::VROverlay()->SetOverlayMouseScale(s.overlay, &scale);
        }
        PlaceChrome(s);  // the height changed
        std::printf("screen %d: buffer %dx%d (surface %dx%d)\n", index + 1, s.width, s.height, s.surfaceWidth,
                    s.surfaceHeight);
    }
    s.key = key, s.buf = *b, s.plain = it->second;
    // While cutting, the next tick draws the new buffer with the cutouts (never floating).
    if (!s.cutting) SetScreenTexture(s, it->second);
    vr::SharedTextureHandle_t handle = it->second;
    vr::Texture_t tex = {&handle, vr::TextureType_SharedTextureHandle, vr::ColorSpace_Gamma};
    for (const auto &[k, sub] : s.subs) vr::VROverlay()->SetOverlayTexture(sub.overlay, &tex);
    s.shown = key;  // UpdateVisibility shows it on the next tick
    return true;
}

void ft_vr_screen_set_surface_size(int index, int width, int height) {
    auto it = g_screens.find(index);
    if (it == g_screens.end()) return;
    Screen &s = it->second;
    if (width == s.surfaceWidth && height == s.surfaceHeight) return;
    s.surfaceWidth = std::max(0, width);
    s.surfaceHeight = std::max(0, height);
    std::printf("screen %d: surface %dx%d (buffer %dx%d)\n", index + 1, s.surfaceWidth, s.surfaceHeight, s.width,
                s.height);
}

void ft_vr_screen_set_output_scale(int index, double scale) {
    auto it = g_screens.find(index);
    if (it == g_screens.end()) return;
    Screen &s = it->second;
    const double sc = std::clamp(scale, 0.5, 4.0);
    if (std::fabs(sc - s.outputScale) < 1e-4) return;
    s.outputScale = sc;
    std::printf("screen %d: output scale %.4f (buffer %dx%d surface %dx%d)\n", index + 1, s.outputScale, s.width,
                s.height, s.surfaceWidth, s.surfaceHeight);
}

double ft_vr_screen_output_scale(int index) {
    auto it = g_screens.find(index);
    return it == g_screens.end() ? 1.0 : it->second.outputScale;
}

void ft_vr_forget(const void *key) {
    if (!g_vr) return;
    if (g_cutterState == 1) g_cutter.Forget(key);
    for (auto &[i, s] : g_screens)
        if (s.key == key) s.key = nullptr;
    auto it = g_imports.find(key);
    if (it == g_imports.end()) return;
    vr::VRIPCResourceManager()->UnrefResource(it->second);
    g_imports.erase(it);
}

void ft_vr_poll(void (*handle)(const struct ft_event *, void *), void *data) {
    if (!g_vr) return;
    RefreshPoses();
    static auto last = Clock::now();
    const auto now = Clock::now();
    const double dt = std::chrono::duration<double>(now - last).count();
    last = now;
    const double step = (dt > 0 && dt < 0.25) ? dt : 0.011;
    UpdateFollow();
    UpdateGaze(step);
    UpdateAttention(step);
    for (auto &[index, s] : g_screens) {
        vr::VREvent_t ev;
        // The screen itself (and a floating window's popups): input for KWin.
        auto panelEvent = [&](const vr::VREvent_t &ev, bool sub) {
            ft_event e{};
            e.screen = index;
            switch (ev.eventType) {
                case vr::VREvent_MouseMove:
                case vr::VREvent_MouseButtonDown:
                case vr::VREvent_MouseButtonUp: {
                    if (ev.eventType == vr::VREvent_MouseMove && s.titleCarry) return;  // KWin stays put
                    // OpenVR reports buffer pixels (bottom-left); convert for the Wayland
                    // seat (coords.h) — see ft_buffer_to_seat for KWin scale vs wl dpr.
                    const double buf_x = ev.data.mouse.x;
                    const double buf_y = s.height - ev.data.mouse.y;
                    double sx = buf_x, sy = buf_y;
                    const int surf_w = s.surfaceWidth > 0 ? s.surfaceWidth : s.width;
                    const int surf_h = s.surfaceHeight > 0 ? s.surfaceHeight : s.height;
                    ft_buffer_to_seat(buf_x, buf_y, s.width, s.height, surf_w, surf_h, s.outputScale, &sx, &sy);
                    if (ev.eventType == vr::VREvent_MouseMove) {
                        e.type = FT_MOTION;
                        if (g_press.buttons) {
                            if (g_dndLogScreen != index) {
                                DndLog("retarget", index);
                                g_dndLogScreen = index;
                            }
                            g_press.screen = index, g_press.x = sx, g_press.y = sy;
                        }
                    } else {
                        if (ev.eventType == vr::VREvent_MouseButtonUp) EndDragsBy(ev.trackedDeviceIndex);
                        e.type = FT_BUTTON;
                        e.button = LinuxButton(ev.data.mouse.button);
                        e.pressed = ev.eventType == vr::VREvent_MouseButtonDown;
                        const bool wasTitleCarry = s.titleCarry;
                        if (!e.pressed && wasTitleCarry) sx = s.carryX, sy = s.carryY, s.titleCarry = false;
                        if (e.pressed) {
                            PressDown(ev.trackedDeviceIndex, e.button, index, sx, sy);
                            // Floating title bar: carry the panel; KWin sees no motion until release.
                            if (!sub && s.floating && e.button == BTN_LEFT && s.titleH > 0 && buf_y >= s.cropY &&
                                buf_y < s.cropY + s.titleH && s.drag == Drag::None) {
                                s.titleCarry = true, s.carryX = sx, s.carryY = sy;
                                StartDrag(s, Drag::Move, ev.trackedDeviceIndex);
                            }
                        } else {
                            // SteamVR often delivers the up to the press-time overlay even after the
                            // laser (and g_press.screen) moved to another panel. Releasing on the
                            // press overlay re-enters it and leaves the Wayland drag stuck on the
                            // seat; finish the drop at the last retargeted panel instead.
                            if ((g_press.buttons & ButtonBit(e.button)) && g_press.screen >= 0 &&
                                g_press.screen != index && !wasTitleCarry) {
                                e.screen = g_press.screen;
                                sx = g_press.x;
                                sy = g_press.y;
                                DndLog("release-retarget", g_press.screen);
                            } else {
                                DndLog("release", index);
                            }
                            g_press.buttons &= ~ButtonBit(e.button);
                            if (!g_press.buttons) g_press.upAt = -1;
                        }
                    }
                    e.x = sx;
                    e.y = sy;
                    break;
                }
                case vr::VREvent_ScrollDiscrete:
                    e.type = FT_SCROLL;
                    e.dx = -ev.data.scroll.xdelta;
                    e.dy = -ev.data.scroll.ydelta;
                    break;
                case vr::VREvent_FocusLeave:
                    if (g_press.buttons) {
                        DndLog("leave-suppressed", index);
                        return;  // keep KWin pointer while a button is held
                    }
                    if (sub) return;              // off a popup is usually onto its window
                    e.type = FT_LEAVE;
                    DndLog("leave", index);
                    break;
                default:
                    return;
            }
            handle(&e, data);
        };
        while (vr::VROverlay()->PollNextOverlayEvent(s.overlay, &ev, sizeof ev)) panelEvent(ev, false);
        for (const auto &[k, sub] : s.subs)
            while (vr::VROverlay()->PollNextOverlayEvent(sub.overlay, &ev, sizeof ev)) panelEvent(ev, true);
        // The controls light up under a laser.
        auto hover = [&](int k) {
            const bool on = ev.eventType == vr::VREvent_MouseMove || ev.eventType == vr::VREvent_FocusEnter;
            if (!on && ev.eventType != vr::VREvent_FocusLeave) return;
            if (s.hover[k] != on) s.hover[k] = on, ApplyAlpha(s);
        };
        // The bar: move (and push/pull with the wheel while moving).
        while (s.bar != vr::k_ulOverlayHandleInvalid &&
               vr::VROverlay()->PollNextOverlayEvent(s.bar, &ev, sizeof ev)) {
            hover(0);
            if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                StartDrag(s, Drag::Move, ev.trackedDeviceIndex);
            else if (ev.eventType == vr::VREvent_MouseButtonUp) {
                EndDragsBy(ev.trackedDeviceIndex);
                ReleaseAwayBy(ev.trackedDeviceIndex, ev.data.mouse.button, handle, data);
            } else if (ev.eventType == vr::VREvent_ScrollDiscrete && s.drag == Drag::Move)
                Push(s, ev.data.scroll.ydelta);
        }
        // The corner: resize.
        while (s.handle != vr::k_ulOverlayHandleInvalid &&
               vr::VROverlay()->PollNextOverlayEvent(s.handle, &ev, sizeof ev)) {
            hover(3);
            if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                StartDrag(s, Drag::Resize, ev.trackedDeviceIndex);
            else if (ev.eventType == vr::VREvent_MouseButtonUp) {
                EndDragsBy(ev.trackedDeviceIndex);
                ReleaseAwayBy(ev.trackedDeviceIndex, ev.data.mouse.button, handle, data);
            }
        }
        // The curve button.
        while (s.curveButton != vr::k_ulOverlayHandleInvalid &&
               vr::VROverlay()->PollNextOverlayEvent(s.curveButton, &ev, sizeof ev)) {
            hover(1);
            if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                ToggleCurve(s);
            else if (ev.eventType == vr::VREvent_MouseButtonUp) {
                EndDragsBy(ev.trackedDeviceIndex);
                ReleaseAwayBy(ev.trackedDeviceIndex, ev.data.mouse.button, handle, data);
            }
        }
        // The roll button: drag around like a knob, or scroll.
        while (s.rollButton != vr::k_ulOverlayHandleInvalid &&
               vr::VROverlay()->PollNextOverlayEvent(s.rollButton, &ev, sizeof ev)) {
            hover(2);
            if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                StartDrag(s, Drag::Roll, ev.trackedDeviceIndex);
            else if (ev.eventType == vr::VREvent_MouseButtonUp) {
                EndDragsBy(ev.trackedDeviceIndex);
                ReleaseAwayBy(ev.trackedDeviceIndex, ev.data.mouse.button, handle, data);
            } else if (ev.eventType == vr::VREvent_ScrollDiscrete && s.drag == Drag::None) {
                Mat p;
                if (!ScreenPose(s, &p)) continue;
                s.rollFrom = s.pinned != kNone ? s.pinRel : p;
                ApplyRoll(s, ev.data.scroll.ydelta * kRollStep * M_PI / 180);
            }
        }
        auto hoverExtra = [&](bool *flag) {
            const bool on = ev.eventType == vr::VREvent_MouseMove || ev.eventType == vr::VREvent_FocusEnter;
            if (!on && ev.eventType != vr::VREvent_FocusLeave) return;
            if (*flag != on) *flag = on, ApplyAlpha(s);
        };
        if (!s.floating) {
            while (vr::VROverlay()->PollNextOverlayEvent(s.anchorButton, &ev, sizeof ev)) {
                hoverExtra(&s.hoverAnchor);
                if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                    CycleScreenAnchor(s);
                else if (ev.eventType == vr::VREvent_MouseButtonUp) {
                    EndDragsBy(ev.trackedDeviceIndex);
                    ReleaseAwayBy(ev.trackedDeviceIndex, ev.data.mouse.button, handle, data);
                }
            }
            while (s.dockButton != vr::k_ulOverlayHandleInvalid &&
                   vr::VROverlay()->PollNextOverlayEvent(s.dockButton, &ev, sizeof ev)) {
                hoverExtra(&s.hoverDock);
                if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                    ToggleScreenDock(index);
                else if (ev.eventType == vr::VREvent_MouseButtonUp) {
                    EndDragsBy(ev.trackedDeviceIndex);
                    ReleaseAwayBy(ev.trackedDeviceIndex, ev.data.mouse.button, handle, data);
                }
            }
        } else {
            // Floating window dock / close (ft-floatd).
            while (s.dockButton != vr::k_ulOverlayHandleInvalid &&
                   vr::VROverlay()->PollNextOverlayEvent(s.dockButton, &ev, sizeof ev)) {
                hoverExtra(&s.hoverDock);
                if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                    SendFloat("dock " + std::to_string(index + 1));
                else if (ev.eventType == vr::VREvent_MouseButtonUp) {
                    EndDragsBy(ev.trackedDeviceIndex);
                    ReleaseAwayBy(ev.trackedDeviceIndex, ev.data.mouse.button, handle, data);
                }
            }
            while (s.closeButton != vr::k_ulOverlayHandleInvalid &&
                   vr::VROverlay()->PollNextOverlayEvent(s.closeButton, &ev, sizeof ev)) {
                hoverExtra(&s.hoverClose);
                if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                    SendFloat("close " + std::to_string(index + 1));
                else if (ev.eventType == vr::VREvent_MouseButtonUp) {
                    EndDragsBy(ev.trackedDeviceIndex);
                    ReleaseAwayBy(ev.trackedDeviceIndex, ev.data.mouse.button, handle, data);
                }
            }
        }
        if (s.drag != Drag::None) UpdateDrag(s, index);
    }
    // A release on the catcher, or the pointer helper's deferred "up".
    vr::VREvent_t catchEv;
    while (g_catcher != vr::k_ulOverlayHandleInvalid &&
           vr::VROverlay()->PollNextOverlayEvent(g_catcher, &catchEv, sizeof catchEv))
        if (catchEv.eventType == vr::VREvent_MouseButtonUp)
            ReleaseAwayBy(catchEv.trackedDeviceIndex, catchEv.data.mouse.button, handle, data);
    if (g_press.upAt >= 0 && g_tick >= g_press.upAt) ReleaseAway(BTN_LEFT, handle, data);
    RefreshChrome();
    vr::VREvent_t ev;
    while (vr::VRSystem()->PollNextEvent(&ev, sizeof ev)) {
        if (ev.eventType == vr::VREvent_Quit) {
            ft_event e{};
            e.type = FT_QUIT;
            handle(&e, data);
        } else if (ev.eventType == vr::VREvent_TrackedDeviceDeactivated) {
            EndDragsBy(ev.trackedDeviceIndex);
        } else if (ev.eventType == vr::VREvent_OverlayCreated) {
            RememberDesktopgameOverlay(ev.data.overlay.overlayHandle);
        } else if (ev.eventType == vr::VREvent_OverlayDestroyed) {
            ForgetDesktopgameOverlay(ev.data.overlay.overlayHandle);
        }
    }
    // Our keyboard: its keys, and its Close key. It goes when the screens do.
    struct Forward {
        void (*handle)(const struct ft_event *, void *);
        void *data;
    } forward{handle, data};
    keyboard::Poll(
        [](const keyboard::Event &k, void *f) {
            ft_event e{};
            e.screen = -1;
            e.type = k.type == keyboard::Event::Key ? FT_KEY : FT_KEYBOARD_CLOSED;
            e.key = k.code;
            e.pressed = k.pressed;
            static_cast<Forward *>(f)->handle(&e, static_cast<Forward *>(f)->data);
        },
        &forward);
    if (g_tick % 9 == 0) UpdateSteamInFront();
    if ((keyboard::Shown() || g_keyboardAside) && !ModeVisible()) {
        g_keyboardAside = false;
        keyboard::Hide();
        ft_event e{};
        e.type = FT_KEYBOARD_CLOSED;
        e.screen = -1;
        handle(&e, data);
    }
    ++g_tick;
    UpdateGame();
    UpdateArrange();
    UpdateVisibility();
    UpdateLasers();
    UpdateControls();
    UpdateGuides();
    UpdateInstrumentAttention(step);
    TickInstruments(step);
    TickToolbar(step);
    UpdateCutouts();
    UpdateCatcher();
}

// Our keyboard (keyboard.cpp) for a screen. It's placed where you'll reach it, not on the
// screen: kKeyboardAhead in front of you (the way your head faces, level) and
// kKeyboardBelow under your eyes, turned to face your eyes, and it stays where it opened
// (or where its grab bar carries it). With Steam in front (UpdateSteamInFront), it waits.
// Without a head pose (the headset is in standby, say) it doesn't open: anywhere else could
// be out of sight or reach. The next text field opens it.
constexpr double kKeyboardAhead = 0.7, kKeyboardBelow = 0.35;

bool ft_vr_keyboard_show(int index) {
    if (!g_vr || g_screens.find(index) == g_screens.end()) return false;
    RefreshPoses();
    Mat head;
    if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head)) {
        std::printf("keyboard: no head pose, not opened\n");
        return false;
    }
    const double fx = -head.m[0][2], fz = -head.m[2][2], n = std::sqrt(fx * fx + fz * fz) + 1e-9;
    const double at[3] = {head.m[0][3] + fx / n * kKeyboardAhead, head.m[1][3] - kKeyboardBelow,
                          head.m[2][3] + fz / n * kKeyboardAhead};
    keyboard::SetLasers(
        g_lasers == Lasers::Always ||
        (g_lasers == Lasers::OutsideGames &&
         !frametop::AppBlocksOutsideGamesLasers(g_appActivity, vr::VROverlay()->IsDashboardVisible())));
    g_steamInFront = SteamInFront();
    if (g_steamInFront) {
        g_asidePose = FacingPose(at, head);
        g_keyboardAside = true;
        std::printf("keyboard: waiting for Steam to close\n");
        return true;
    }
    return keyboard::Show(FacingPose(at, head));
}

void ft_vr_keyboard_hide(void) {
    g_keyboardAside = false;
    if (g_vr) keyboard::Hide();
}

// Control commands (datagrams on @ft_screens, replies to the sender):
//   place <screen> <x> <y> <z> <yaw> <pitch> <roll>   centre (standing universe) and facing
//   width <screen> <metres>
//   curve <screen> <radius>   cylinder radius in metres; 0 = flat
//   curve <screen> on|off     on: the radius is the head's distance to it now -> "ok <radius>"
//   pin <screen|all> <left|right|head> [12 numbers]   pin to that anchor: as it is now,
//                             or at the given device->screen transform (rows of a 3x4)
//   unpin <screen|all>
//   opacity <screen> <active> [idle]
//   attention <screen> on|off [inMs outMs dwellMs holdMs]
//   deadzone <screen> on|off [degrees [metres]]   soft-follow glance dead zone
//   gaze state|debug on|off|fallback head|fallback off
//   get <screen>  -> "ok ... width height curve activeOpacity idleOpacity anchor [rel...]"
//   screens       -> "ok <count> <index>:<pixels w>x<h>:<metres> ..."
//   head          -> "ok x y z yaw"
//   visibility always|dashboard|gesture|toggle
//   wrist <degrees>           a controller-pinned screen shows while you see its front within this
//   gesture <left|right> <degrees>   the gesture mode: look within this of that controller
//   hide | show | toggle      the manual switch (see g_manual)
//   conceal <screen|all> | reveal <screen|all>   a screen hidden on its own, whatever the mode
//   concealed     -> "ok [<screen> ...]"   the screens hidden on their own
// Floating windows (from ft-floatd; <screen> is the spare output's number, after the screens):
//   float <screen> <metres per pixel> <x> <y> <w> <h> <title>   the window's rectangle in the
//                             buffer and its title bar's height (pixels); shows the panel
//   unfloat <screen>          hides it
//   pose <screen> <12 numbers>  its place in the room (rows of a 3x4, standing universe)
//   sub <screen> <k> <x> <y> <w> <h> | sub <screen> <k> off   popup or dialog k over it
//   minimized <screen> 0|1
//   carry <screen>            the window's own title bar was pressed (an app that draws its
//                             own): carry the panel with the pressing laser until the release
//   up                        pointer helper: left button came up off our overlays
//   controllers always|outside_games|dashboard   when controllers' lasers work the screens
//   ingames hide|visible      during a VR/flat game, hide makes every normal visibility mode
//                             yield to the game until the dashboard/manual override shows it
//   state         -> "ok <mode> <manual 0|1> <wrist deg> <gesture hand> <gesture deg>
//                     <controllers> <game running 0|1> <ingames> <app_activity>"
// (size <screen> <w> <h> and key <code> <value> are handled in compositor.c.) Screens are
// numbered from 1 here, like everywhere the user sees them. "screens" and "all" leave out
// floating windows.
void ft_vr_command(const char *cmd, char *reply, int size) {
    if (!g_vr) return (void)std::snprintf(reply, size, "error no SteamVR (--no-vr)");
    RefreshPoses();
    int n;
    double x, y, z, yaw, pitch, roll, w;
    char word[32], hand[32], filled[64];
    float r[12];
    auto each = [&](const char *which, auto fn) -> bool {  // "all" or a screen number
        if (std::strcmp(which, "all") == 0) {
            for (auto &[i, s] : g_screens)
                if (!s.floating) fn(s);
            return true;
        }
        Screen *s = Find(std::atoi(which));
        if (s && !s->floating) fn(*s);
        return s != nullptr && !s->floating;
    };
    if (std::sscanf(cmd, "place %d %lf %lf %lf %lf %lf %lf", &n, &x, &y, &z, &yaw, &pitch, &roll) == 7) {
        Screen *s = Find(n);
        if (!s) return (void)std::snprintf(reply, size, "error no screen %d", n);
        EndDrag(*s);
        SetAbsolute(*s, PanelPose(x, y, z, yaw, pitch, roll));
        std::snprintf(reply, size, "ok");
    } else if (std::sscanf(cmd, "width %d %lf", &n, &w) == 2) {
        Screen *s = Find(n);
        if (!s) return (void)std::snprintf(reply, size, "error no screen %d", n);
        SetWidth(*s, w);
        std::snprintf(reply, size, "ok");
    } else if (std::sscanf(cmd, "curve %d %7s", &n, word) == 2 && (!std::strcmp(word, "on") || !std::strcmp(word, "off"))) {
        Screen *s = Find(n);
        if (!s) return (void)std::snprintf(reply, size, "error no screen %d", n);
        if ((s->curve > 0) != (word[1] == 'n')) ToggleCurve(*s);
        std::snprintf(reply, size, "ok %.3f", s->curve);
    } else if (std::sscanf(cmd, "curve %d %lf", &n, &w) == 2) {
        Screen *s = Find(n);
        if (!s) return (void)std::snprintf(reply, size, "error no screen %d", n);
        s->curve = w > 0 ? std::max(0.5, w) : 0;
        ApplyCurve(*s);
        PlaceChrome(*s);
        std::snprintf(reply, size, "ok");
    } else if (const int got = std::sscanf(cmd, "pin %15s %31s %f %f %f %f %f %f %f %f %f %f %f %f", word, hand,
                                           &r[0], &r[1], &r[2], &r[3], &r[4], &r[5], &r[6], &r[7], &r[8], &r[9],
                                           &r[10], &r[11]);
               got >= 2) {
        const AnchorMode mode = ParseAnchorMode(hand);
        if (std::strcmp(hand, "left") && std::strcmp(hand, "right") && std::strcmp(hand, "head") &&
            std::strcmp(hand, "head-rigid") && std::strcmp(hand, "yaw-follow") &&
            std::strcmp(hand, "position-follow") && std::strcmp(hand, "world"))
            return (void)std::snprintf(reply, size,
                                       "error anchors: left right head head-rigid yaw-follow position-follow world");
        Mat rel = Identity();
        for (int k = 0; k < 12; ++k) rel.m[k / 4][k % 4] = r[k];
        const bool found = each(word, [&](Screen &s) {
            Mat p, hmd;
            EndDrag(s);
            if (mode == AnchorMode::World) {
                if (ScreenPose(s, &p)) SetAbsolute(s, p);
                return;
            }
            if (got == 14) {
                SetFollow(s, mode, rel);
                return;
            }
            if (!ScreenPose(s, &p)) return;
            if (IsRigidDevice(mode)) {
                const auto dev = DeviceForMode(mode);
                Mat c;
                if (dev == kNone || !DevicePose(dev, &c)) return;
                SetFollow(s, mode, Mul(Inverse(c), p));
            } else {
                if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &hmd)) return;
                SetFollow(s, mode, Mul(Inverse(ReferenceFrame(mode, hmd)), p));
            }
            RefreshSlotTextures(s);
        });
        std::snprintf(reply, size, found ? "ok" : "error no such screen");
    } else if (std::sscanf(cmd, "unpin %15s", word) == 1) {
        const bool found = each(word, [&](Screen &s) {
            Mat p;
            if (ScreenPose(s, &p)) SetAbsolute(s, p);
            RefreshSlotTextures(s);
        });
        std::snprintf(reply, size, found ? "ok" : "error no such screen");
    } else if (int opacityGot = std::sscanf(cmd, "opacity %d %lf %lf", &n, &w, &x); opacityGot >= 2) {
        Screen *s = Find(n);
        if (!s) return (void)std::snprintf(reply, size, "error no screen %d", n);
        const float active = float(std::clamp(w, 0.0, 1.0));
        const float idle = opacityGot >= 3 ? float(std::clamp(x, 0.0, 1.0)) : active;
        SetScreenOpacity(*s, active, idle);
        std::snprintf(reply, size, "ok %.3f %.3f", s->activeOpacity, s->idleOpacity);
    } else if (std::sscanf(cmd, "scale %d %lf", &n, &w) == 2) {
        Screen *s = Find(n);
        if (!s) return (void)std::snprintf(reply, size, "error no screen %d", n);
        ft_vr_screen_set_output_scale(n - 1, w);
        std::snprintf(reply, size, "ok %.4f", s->outputScale);
    } else if (std::sscanf(cmd, "attention %d %15s", &n, word) >= 2) {
        Screen *s = Find(n);
        if (!s) return (void)std::snprintf(reply, size, "error no screen %d", n);
        if (!std::strcmp(word, "off")) {
            s->attentionEnabled = false;
            s->attentionFocused = false;
            s->attentionResolved = s->activeOpacity;
        } else {
            s->attentionEnabled = true;
            // attention N on [inMs [outMs [dwellMs [holdMs]]]]
            double inMs = s->attentionInMs, outMs = s->attentionOutMs, dwell = s->attentionDwellMs,
                   hold = s->attentionHoldMs;
            const int got = std::sscanf(cmd, "attention %*d %*s %lf %lf %lf %lf", &inMs, &outMs, &dwell, &hold);
            if (got >= 1) s->attentionInMs = std::clamp(inMs, 20.0, 2000.0);
            if (got >= 2) s->attentionOutMs = std::clamp(outMs, 20.0, 2000.0);
            if (got >= 3) s->attentionDwellMs = std::clamp(dwell, 0.0, 1000.0);
            if (got >= 4) s->attentionHoldMs = std::clamp(hold, 0.0, 1000.0);
        }
        ApplyAlpha(*s);
        std::snprintf(reply, size, "ok");
    } else if (std::sscanf(cmd, "deadzone %d %15s", &n, word) >= 2) {
        Screen *s = Find(n);
        if (!s) return (void)std::snprintf(reply, size, "error no screen %d", n);
        if (!std::strcmp(word, "off")) {
            s->followDeadzone = false;
            s->followLockValid = false;
        } else {
            s->followDeadzone = true;
            double deg = s->followDeadzoneDeg, metres = s->followDeadzoneM;
            const int got = std::sscanf(cmd, "deadzone %*d %*s %lf %lf", &deg, &metres);
            if (got >= 1) s->followDeadzoneDeg = std::clamp(deg, 1.0, 90.0);
            if (got >= 2) s->followDeadzoneM = std::clamp(metres, 0.02, 1.0);
            // Re-seed lock from current head so enabling doesn't yank the panel.
            Mat hmd;
            if (IsSoftFollow(s->anchor) && DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &hmd)) {
                s->followLock = ReferenceFrame(s->anchor, hmd);
                s->followLockValid = true;
            } else {
                s->followLockValid = false;
            }
        }
        std::snprintf(reply, size, "ok %s %.1f %.3f", s->followDeadzone ? "on" : "off", s->followDeadzoneDeg,
                      s->followDeadzoneM);
    } else if (std::strncmp(cmd, "gaze ", 5) == 0) {
        if (!std::strcmp(cmd + 5, "state")) {
            const char *kind = "none";
            switch (g_gazeTarget.kind) {
                case GazeKind::Screen: kind = "screen"; break;
                case GazeKind::Bar: kind = "bar"; break;
                case GazeKind::Curve: kind = "curve"; break;
                case GazeKind::Roll: kind = "roll"; break;
                    case GazeKind::Resize: kind = "resize"; break;
                case GazeKind::Anchor: kind = "anchor"; break;
                case GazeKind::Slot: kind = "slot"; break;
                case GazeKind::Instrument: kind = "instrument"; break;
                case GazeKind::Dock: kind = "dock"; break;
                case GazeKind::Toolbar: kind = "toolbar"; break;
                default: break;
            }
            int px = 0, py = 0, bpx = 0, bpy = 0;
            int surf_w = 0, surf_h = 0, buf_w = 0, buf_h = 0;
            if (g_gazeTarget) {
                auto it = g_screens.find(g_gazeTarget.screen);
                if (it != g_screens.end()) {
                    const Screen &gs = it->second;
                    buf_w = gs.width;
                    buf_h = gs.height;
                    surf_w = gs.surfaceWidth > 0 ? gs.surfaceWidth : gs.width;
                    surf_h = gs.surfaceHeight > 0 ? gs.surfaceHeight : gs.height;
                    if (g_gazeTarget.kind == GazeKind::Screen) {
                        bpx = int(std::lround(g_gazeTarget.u * buf_w));
                        bpy = int(std::lround(g_gazeTarget.v * buf_h));
                        double sx = 0, sy = 0;
                        ft_uv_to_seat(g_gazeTarget.u, g_gazeTarget.v, buf_w, buf_h, surf_w, surf_h, gs.outputScale,
                                      &sx, &sy);
                        px = int(std::lround(sx));
                        py = int(std::lround(sy));
                    }
                }
            }
            std::snprintf(reply, size,
                          "ok eye=%d valid=%d held=%d fallback=%d err=%d flags=%d origin=%.4f,%.4f,%.4f dir=%.4f,%.4f,%.4f "
                          "target=%s screen=%d slot=%d u=%.4f v=%.4f pixel=%d,%d buffer_pixel=%d,%d "
                          "surface=%dx%d buffer=%dx%d dist=%.4f",
                          g_eyeAvailable ? 1 : 0, g_eyeValid ? 1 : 0, g_eyeHeld ? 1 : 0, g_gazeFallbackHead ? 1 : 0,
                          g_eyeLastErr, g_eyeFlags, g_gazeOrigin[0], g_gazeOrigin[1], g_gazeOrigin[2], g_gazeDir[0],
                          g_gazeDir[1], g_gazeDir[2], kind, g_gazeTarget.screen + 1, g_gazeTarget.slot + 1,
                          g_gazeTarget.u,
                          g_gazeTarget.v, px, py, bpx, bpy, surf_w, surf_h, buf_w, buf_h, g_gazeTarget.distance);
        } else if (!std::strcmp(cmd + 5, "debug on")) {
            g_gazeDebug = true;
            std::snprintf(reply, size, "ok debug on");
        } else if (!std::strcmp(cmd + 5, "debug off")) {
            g_gazeDebug = false;
            std::snprintf(reply, size, "ok debug off");
        } else if (!std::strcmp(cmd + 5, "fallback head")) {
            g_gazeFallbackHead = true;
            std::snprintf(reply, size, "ok fallback=head (debug only; not silent eye substitution)");
        } else if (!std::strcmp(cmd + 5, "fallback off")) {
            g_gazeFallbackHead = false;
            std::snprintf(reply, size, "ok fallback=off");
        } else {
            std::snprintf(reply, size,
                          "error gaze state|debug on|off|fallback head|off");
        }
    } else if (std::sscanf(cmd, "followlag %lf", &w) == 1) {
        g_followLagMs = std::clamp(w, 0.0, 1000.0);
        std::snprintf(reply, size, "ok %.0f", g_followLagMs);
    } else if (std::sscanf(cmd, "slots-state %d %63s", &n, filled) == 2) {
        g_currentSlot = std::clamp(n, 0, kSlotCount);
        for (int i = 0; i < kSlotCount; ++i) g_slotFilled[i] = false;
        if (std::strcmp(filled, "-")) {
            char *p = filled;
            while (*p) {
                int slot = std::strtol(p, &p, 10);
                if (slot >= 1 && slot <= kSlotCount) g_slotFilled[slot - 1] = true;
                if (*p == ',') ++p;
            }
        }
        for (auto &[i, s] : g_screens) RefreshSlotTextures(s);
        std::snprintf(reply, size, "ok");
    } else if (std::sscanf(cmd, "get %d", &n) == 1) {
        Screen *s = Find(n);
        Mat m;
        if (!s) return (void)std::snprintf(reply, size, "error no screen %d", n);
        if (!ScreenPose(*s, &m)) return (void)std::snprintf(reply, size, "error screen %d has no pose", n);
        int len = std::snprintf(
            reply, size,
            "ok %.4f %.4f %.4f  %.5f %.5f %.5f  %.5f %.5f %.5f  %.5f %.5f %.5f  %.4f %.4f %.3f %.3f %.3f %s",
            m.m[0][3], m.m[1][3], m.m[2][3], m.m[0][0], m.m[1][0], m.m[2][0], m.m[0][1], m.m[1][1], m.m[2][1],
            m.m[0][2], m.m[1][2], m.m[2][2], s->metres, s->heightMetres(), s->curve, s->activeOpacity,
            s->idleOpacity, AnchorModeName(s->anchor));
        if (s->anchor != AnchorMode::World)
            for (int k = 0; k < 12 && len < size; ++k)
                len += std::snprintf(reply + len, size - len, " %.5f", s->pinRel.m[k / 4][k % 4]);
    } else if (std::strncmp(cmd, "screens", 7) == 0) {
        size_t n = 0;
        for (auto &[i, s] : g_screens)
            if (!s.floating) ++n;
        int len = std::snprintf(reply, size, "ok %zu", n);
        for (auto &[i, s] : g_screens)
            if (!s.floating && len < size)
                len += std::snprintf(reply + len, size - len, " %d:%dx%d:%.3f", i + 1, s.width, s.height, s.metres);
    } else if (std::strncmp(cmd, "head", 4) == 0) {
        Mat m;
        if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &m))
            return (void)std::snprintf(reply, size, "error no head pose (headset off?)");
        std::snprintf(reply, size, "ok %.4f %.4f %.4f %.2f", m.m[0][3], m.m[1][3], m.m[2][3],
                      std::atan2(m.m[0][2], m.m[2][2]) * 180 / M_PI);
    } else if (std::sscanf(cmd, "visibility %31s", word) == 1) {
        const std::string m = word;
        if (m == "always") g_mode = Mode::Always;
        else if (m == "dashboard") g_mode = Mode::Dashboard;
        else if (m == "except_dashboard") g_mode = Mode::ExceptDashboard;
        else if (m == "gesture") g_mode = Mode::Gesture;
        else if (m == "toggle") g_mode = Mode::Toggle;
        else return (void)std::snprintf(reply, size,
            "error modes: always dashboard except_dashboard gesture toggle");
        g_manual = false;
        std::snprintf(reply, size, "ok %s", ModeName());
    } else if (std::sscanf(cmd, "wrist %lf", &w) == 1) {
        g_wristAngle = std::clamp(w, 10.0, 180.0);
        std::snprintf(reply, size, "ok");
    } else if (std::sscanf(cmd, "gesture %15s %lf", hand, &w) == 2) {
        g_gestureHand = std::strcmp(hand, "right") == 0 ? "right" : "left";
        g_gestureAngle = std::clamp(w, 5.0, 90.0);
        std::snprintf(reply, size, "ok");
    } else if (int x0, y0, w0, h0, t0; std::sscanf(cmd, "float %d %lf %d %d %d %d %d", &n, &w, &x0, &y0, &w0, &h0,
                                                    &t0) == 7) {
        Screen *s = Find(n);
        if (!s || !s->floating) return (void)std::snprintf(reply, size, "error no floating window panel %d", n);
        if (!(w > 1e-5 && w < 0.01) || w0 < 1 || h0 < 1) return (void)std::snprintf(reply, size, "error bad float");
        SetFloat(*s, w, x0, y0, w0, h0, std::max(0, t0));
        std::snprintf(reply, size, "ok");
    } else if (std::sscanf(cmd, "unfloat %d", &n) == 1) {
        Screen *s = Find(n);
        if (!s || !s->floating) return (void)std::snprintf(reply, size, "error no floating window panel %d", n);
        Unfloat(*s);
        UpdateVisibility();
        std::snprintf(reply, size, "ok");
    } else if (std::sscanf(cmd, "pose %d %f %f %f %f %f %f %f %f %f %f %f %f", &n, &r[0], &r[1], &r[2], &r[3], &r[4],
                           &r[5], &r[6], &r[7], &r[8], &r[9], &r[10], &r[11]) == 13) {
        Screen *s = Find(n);
        if (!s) return (void)std::snprintf(reply, size, "error no screen %d", n);
        Mat m{};
        for (int k = 0; k < 12; ++k) m.m[k / 4][k % 4] = r[k];
        EndDrag(*s);
        SetAbsolute(*s, m);
        std::snprintf(reply, size, "ok");
    } else if (int k0 = 0, sx0 = 0, sy0 = 0, sw0 = 0, sh0 = 0;
               std::sscanf(cmd, "sub %d %d %d %d %d %d", &n, &k0, &sx0, &sy0, &sw0, &sh0) == 6 ||
               (std::sscanf(cmd, "sub %d %d %15s", &n, &k0, word) == 3 && !std::strcmp(word, "off"))) {
        Screen *s = Find(n);
        if (!s || !s->floating) return (void)std::snprintf(reply, size, "error no floating window panel %d", n);
        if (std::strstr(cmd, " off")) sw0 = sh0 = 0;
        SetSub(*s, n - 1, k0, sx0, sy0, sw0, sh0);
        std::snprintf(reply, size, "ok");
    } else if (int on; std::sscanf(cmd, "minimized %d %d", &n, &on) == 2) {
        Screen *s = Find(n);
        if (!s || !s->floating) return (void)std::snprintf(reply, size, "error no floating window panel %d", n);
        s->minimized = on != 0;
        UpdateVisibility();
        std::snprintf(reply, size, "ok");
    } else if (std::sscanf(cmd, "carry %d", &n) == 1) {
        Screen *s = Find(n);
        if (!s || !s->floating) return (void)std::snprintf(reply, size, "error no floating window panel %d", n);
        if (!(g_press.buttons & ButtonBit(BTN_LEFT)) || g_press.screen != n - 1 || s->drag != Drag::None)
            return (void)std::snprintf(reply, size, "error not pressed there");
        s->titleCarry = true, s->carryX = g_press.x, s->carryY = g_press.y;
        StartDrag(*s, Drag::Move, g_press.device);
        std::snprintf(reply, size, "ok");
    } else if (std::strcmp(cmd, "up") == 0) {
        if ((g_press.buttons & ButtonBit(BTN_LEFT)) && g_press.device != kNone && !IsHandController(g_press.device))
            g_press.upAt = g_tick + 9;
        std::snprintf(reply, size, "ok");
    } else if (std::strncmp(cmd, "concealed", 9) == 0) {
        // Checked before "conceal %s": sscanf's space matches nothing, so "concealed" would parse as "conceal ed".
        int len = std::snprintf(reply, size, "ok");
        for (auto &[i, s] : g_screens)
            if (len < size && s.alone && !s.floating) len += std::snprintf(reply + len, size - len, " %d", i + 1);
    } else if (std::sscanf(cmd, "conceal %15s", word) == 1 || std::sscanf(cmd, "reveal %15s", word) == 1) {
        const bool conceal = cmd[0] == 'c';
        if (std::strcmp(word, "all")) {
            Screen *s = Find(std::atoi(word));
            if (!s || s->floating) return (void)std::snprintf(reply, size, "error no screen %s", word);
        }
        each(word, [&](Screen &s) { s.alone = conceal; });  // each already skips floats
        UpdateVisibility();
        std::snprintf(reply, size, "ok");
    } else if (!std::strncmp(cmd, "hide", 4) || !std::strncmp(cmd, "show", 4) || !std::strncmp(cmd, "toggle", 6)) {
        const Mode eff = EffectiveMode();
        const bool dashOpen = vr::VROverlay()->IsDashboardVisible();
        // Always: manual means hidden. Dashboard/gesture/toggle: manual means force-shown.
        // ExceptDashboard: Always polarity with dashboard closed; force-show while open.
        const bool manualMeansHidden =
            eff == Mode::Always || (eff == Mode::ExceptDashboard && !dashOpen);
        const bool shownNow = manualMeansHidden ? !g_manual : g_manual;
        const bool want = cmd[0] == 's' ? true : cmd[0] == 'h' ? false : !shownNow;
        g_manual = manualMeansHidden ? !want : want;
        UpdateVisibility();
        std::snprintf(reply, size, "ok %s", want ? "shown" : "hidden");
    } else if (std::sscanf(cmd, "ingames %15s", word) == 1) {
        if (!std::strcmp(word, "hide")) g_inGames = InGames::Hide;
        else if (!std::strcmp(word, "visible")) g_inGames = InGames::Visible;
        else return (void)std::snprintf(reply, size, "error modes: hide visible");
        g_manual = false;
        UpdateVisibility();
        std::snprintf(reply, size, "ok %s", word);
    } else if (std::sscanf(cmd, "controllers %15s", word) == 1) {
        const std::string m = word;
        if (m == "always") g_lasers = Lasers::Always;
        else if (m == "outside_games") g_lasers = Lasers::OutsideGames;
        else if (m == "dashboard") g_lasers = Lasers::Dashboard;
        else return (void)std::snprintf(reply, size, "error modes: always outside_games dashboard");
        UpdateLasers();
        std::snprintf(reply, size, "ok %s", LasersName());
    } else if (std::sscanf(cmd, "cutouts %15s", word) == 1) {
        char arg[16] = "";
        double ms = 0;
        if (!std::strcmp(word, "on")) g_cutouts = true;
        else if (!std::strcmp(word, "off")) g_cutouts = false;
        else if (!std::strcmp(word, "predict") && std::sscanf(cmd, "cutouts predict %15s", arg) == 1 &&
                 (!std::strcmp(arg, "on") || !std::strcmp(arg, "off")))
            g_hands.SetPrediction(!std::strcmp(arg, "on"), g_hands.leadMs());
        else if (!std::strcmp(word, "lead") && std::sscanf(cmd, "cutouts lead %lf", &ms) == 1)
            g_hands.SetPrediction(g_hands.predicting(), ms);
        else if (std::strcmp(word, "state") != 0)
            return (void)std::snprintf(reply, size, "error cutouts on|off|state|predict on|off|lead <ms>");
        std::snprintf(reply, size, "ok %s predict %s lead %.0f ms cutter %d", g_cutouts ? "on" : "off",
                      g_hands.predicting() ? "on" : "off", g_hands.leadMs(), g_cutterState);
    } else if (std::strncmp(cmd, "state", 5) == 0) {
        std::snprintf(reply, size, "ok %s %d %.0f %s %.0f %s %d %s %s", ModeName(), g_manual ? 1 : 0, g_wristAngle,
                      g_gestureHand.c_str(), g_gestureAngle, LasersName(), g_gameRunning ? 1 : 0,
                      g_inGames == InGames::Hide ? "hide" : "visible",
                      frametop::AppActivityName(g_appActivity));
    } else if (std::strncmp(cmd, "instrument ", 11) == 0 || !std::strcmp(cmd, "instrument")) {
        const char *rest = cmd + (std::strncmp(cmd, "instrument ", 11) == 0 ? 11 : 10);
        char id[64] = {};
        if (!std::strcmp(rest, "clear") || !std::strncmp(rest, "clear ", 6)) {
            ClearInstruments();
            std::snprintf(reply, size, "ok");
        } else if (!std::strcmp(rest, "list")) {
            int len = std::snprintf(reply, size, "ok %zu", g_instruments.size());
            for (auto &inst : g_instruments)
                if (len < size)
                    len += std::snprintf(reply + len, size - len, " %s:%s:%d", inst.id.c_str(),
                                         InstrumentTypeName(inst.type), inst.enabled ? 1 : 0);
        } else if (std::sscanf(rest, "enable %63s", id) == 1) {
            if (!KnownInstrumentId(id))
                return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
            Instrument &inst = FindOrCreateInstrument(id);
            EnableInstrument(inst, true);
            if (IsIdentityMat(inst.pose)) RecenterInstrument(inst);
            std::snprintf(reply, size, "ok");
        } else if (std::sscanf(rest, "disable %63s", id) == 1) {
            Instrument *inst = FindInstrument(id);
            if (!inst) return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
            EnableInstrument(*inst, false);
            std::snprintf(reply, size, "ok");
        } else if (std::sscanf(rest, "recenter %63s", id) == 1) {
            if (!KnownInstrumentId(id))
                return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
            Instrument &inst = FindOrCreateInstrument(id);
            EnableInstrument(inst, true);
            RecenterInstrument(inst);
            std::snprintf(reply, size, "ok");
        } else if (std::sscanf(rest, "width %63s %lf", id, &w) == 2) {
            Instrument *inst = FindInstrument(id);
            if (!inst) return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
            SetInstrumentWidth(*inst, w);
            std::snprintf(reply, size, "ok");
        } else if (int og = std::sscanf(rest, "opacity %63s %lf %lf", id, &w, &x); og >= 2) {
            Instrument *inst = FindInstrument(id);
            if (!inst) return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
            SetInstrumentOpacity(*inst, float(w), float(og >= 3 ? x : w));
            std::snprintf(reply, size, "ok");
        } else if (std::sscanf(rest, "color %63s %63s", id, filled) == 2) {
            Instrument *inst = FindInstrument(id);
            if (!inst) return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
            uint8_t cr, cg, cb;
            if (!ParseInstrumentColor(filled, &cr, &cg, &cb))
                return (void)std::snprintf(reply, size, "error color wants #RRGGBB");
            SetInstrumentColor(*inst, cr, cg, cb);
            std::snprintf(reply, size, "ok");
        } else if (std::sscanf(rest, "attention %63s %15s", id, word) == 2) {
            Instrument *inst = FindInstrument(id);
            if (!inst) return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
            inst->attentionEnabled = std::strcmp(word, "off") != 0;
            if (!inst->attentionEnabled) inst->attentionResolved = inst->activeOpacity;
            ApplyInstrumentAlpha(*inst);
            std::snprintf(reply, size, "ok");
        } else if (std::sscanf(rest, "place %63s %lf %lf %lf %lf %lf %lf", id, &x, &y, &z, &yaw, &pitch, &roll) == 7) {
            Instrument *inst = FindInstrument(id);
            if (!inst) {
                if (!KnownInstrumentId(id))
                    return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
                inst = &FindOrCreateInstrument(id);
            }
            EndInstrumentDrag(*inst);
            SetInstrumentAbsolute(*inst, PanelPose(x, y, z, yaw, pitch, roll));
            ShowInstrument(*inst, inst->enabled);
            std::snprintf(reply, size, "ok");
        } else if (std::sscanf(rest, "unpin %63s", id) == 1) {
            Instrument *inst = FindInstrument(id);
            if (!inst) return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
            Mat p;
            if (InstrumentPose(*inst, &p)) SetInstrumentAbsolute(*inst, p);
            std::snprintf(reply, size, "ok");
        } else if (const int got = std::sscanf(rest, "pin %63s %31s %f %f %f %f %f %f %f %f %f %f %f %f", id, hand,
                                               &r[0], &r[1], &r[2], &r[3], &r[4], &r[5], &r[6], &r[7], &r[8], &r[9],
                                               &r[10], &r[11]);
                   got >= 2) {
            Instrument *inst = FindInstrument(id);
            if (!inst) return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
            const AnchorMode mode = ParseAnchorMode(hand);
            Mat rel = Identity();
            if (got >= 14) {
                for (int k = 0; k < 12; ++k) rel.m[k / 4][k % 4] = r[k];
            } else {
                Mat p, hmd;
                if (!InstrumentPose(*inst, &p) || !DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &hmd))
                    return (void)std::snprintf(reply, size, "error no pose");
                rel = Mul(Inverse(ReferenceFrame(mode, hmd)), p);
            }
            if (mode == AnchorMode::World) {
                Mat p;
                if (InstrumentPose(*inst, &p)) SetInstrumentAbsolute(*inst, p);
            } else {
                SetInstrumentFollow(*inst, mode, rel);
            }
            ShowInstrument(*inst, inst->enabled);
            std::snprintf(reply, size, "ok");
        } else if (std::sscanf(rest, "get %63s", id) == 1) {
            Instrument *inst = FindInstrument(id);
            Mat m;
            if (!inst) return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
            if (!InstrumentPose(*inst, &m))
                return (void)std::snprintf(reply, size, "error instrument %s has no pose", id);
            int len = std::snprintf(
                reply, size,
                "ok %.4f %.4f %.4f  %.5f %.5f %.5f  %.5f %.5f %.5f  %.5f %.5f %.5f  %.4f %.4f %.3f %.3f %.3f %d %s",
                m.m[0][3], m.m[1][3], m.m[2][3], m.m[0][0], m.m[1][0], m.m[2][0], m.m[0][1], m.m[1][1], m.m[2][1],
                m.m[0][2], m.m[1][2], m.m[2][2], inst->metres, inst->heightMetres(), 0.0, inst->activeOpacity,
                inst->idleOpacity, inst->attentionEnabled ? 1 : 0, AnchorModeName(inst->anchor));
            if (inst->anchor != AnchorMode::World)
                for (int k = 0; k < 12 && len < size; ++k)
                    len += std::snprintf(reply + len, size - len, " %.5f", inst->pinRel.m[k / 4][k % 4]);
        } else if (!std::strncmp(rest, "file ", 5)) {
            char path[512] = {};
            if (std::sscanf(rest + 5, "%63s %511[^\n]", id, path) != 2)
                return (void)std::snprintf(reply, size, "error instrument file wants id path");
            if (!IsImageInstrumentId(id) && !IsLauncherInstrumentId(id))
                return (void)std::snprintf(reply, size, "error instrument file is only for image/launcher ids");
            Instrument &inst = FindOrCreateInstrument(id);
            if (!SetInstrumentImagePath(inst, path))
                return (void)std::snprintf(reply, size, "error failed to load image");
            // File used to load pixels without enabling — UI said on, VR stayed blank.
            EnableInstrument(inst, true);
            if (IsIdentityMat(inst.pose) && inst.pinned == kNone) RecenterInstrument(inst);
            std::snprintf(reply, size, "ok");
        } else if (!std::strncmp(rest, "launcher ", 9)) {
            char kind[32] = {}, arg1[512] = {};
            const char *p = rest + 9;
            if (std::sscanf(p, "%63s %31s %511[^\n]", id, kind, arg1) < 2)
                return (void)std::snprintf(reply, size, "error instrument launcher wants id kind …");
            if (!IsLauncherInstrumentId(id))
                return (void)std::snprintf(reply, size, "error not a launcher id");
            Instrument &inst = FindOrCreateInstrument(id);
            if (!std::strcmp(kind, "application")) {
                inst.launchKind = "application";
                inst.launchTarget = arg1[0] ? arg1 : "-";
                inst.launchCommandJson.clear();
            } else if (!std::strcmp(kind, "action")) {
                inst.launchKind = "action";
                inst.launchTarget = arg1[0] ? arg1 : "-";
                inst.launchCommandJson.clear();
            } else if (!std::strcmp(kind, "shell")) {
                inst.launchKind = "shell";
                std::string raw = arg1;
                if (raw.size() >= 2 && raw.front() == '"' && raw.back() == '"') {
                    std::string out;
                    for (size_t i = 1; i + 1 < raw.size(); ++i) {
                        if (raw[i] == '\\' && i + 1 < raw.size()) {
                            const char n = raw[++i];
                            if (n == 'n') out.push_back('\n');
                            else if (n == 't') out.push_back('\t');
                            else if (n == '"' || n == '\\') out.push_back(n);
                            else out.push_back(n);
                        } else
                            out.push_back(raw[i]);
                    }
                    inst.launchTarget = out;
                } else {
                    inst.launchTarget = raw;
                }
                inst.launchCommandJson.clear();
            } else if (!std::strcmp(kind, "command")) {
                inst.launchKind = "command";
                inst.launchCommandJson = arg1[0] ? arg1 : "[]";
                inst.launchTarget.clear();
            } else if (!std::strcmp(kind, "appear")) {
                char mode[32] = {}, glyph[64] = {};
                if (std::sscanf(arg1, "%31s %63s", mode, glyph) < 1)
                    return (void)std::snprintf(reply, size, "error appear wants mode");
                inst.launchAppear = mode;
                if (glyph[0]) inst.launchGlyph = glyph;
                if (inst.launchAppear != "app" && inst.launchAppear != "glyph" && inst.launchAppear != "image" &&
                    inst.launchAppear != "fallback")
                    inst.launchAppear = "fallback";
                inst.lastLauncherKey = -1;
                RefreshLauncherTexture(inst, true);
            } else {
                return (void)std::snprintf(reply, size,
                                           "error launcher kind want application|action|shell|command|appear");
            }
            std::snprintf(reply, size, "ok");
        } else {
            std::snprintf(reply, size, "error instrument commands: list|get|enable|disable|place|width|pin|unpin|"
                                       "opacity|color|attention|recenter|file|launcher|clear");
        }
    } else if (std::strncmp(cmd, "toolbar ", 8) == 0 || !std::strcmp(cmd, "toolbar")) {
        ToolbarCommand(cmd + (std::strncmp(cmd, "toolbar ", 8) == 0 ? 8 : 7), reply, size);
    } else if (std::strncmp(cmd, "dock ", 5) == 0) {
        DockCommand(cmd + 5, reply, size);
    } else {
        std::snprintf(reply, size, "error unknown command");
    }
}

}  // extern "C"
