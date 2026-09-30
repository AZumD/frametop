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
//     open, while you look at a chosen controller (the wrist gesture), or toggle only
//     (hidden until the hotkey shows them).
//   - controllers on the screens: while visible, the screens can keep SteamVR's laser mouse
//     on (VROverlayFlags_MakeOverlaysInteractiveIfVisible), so controllers use them with
//     the dashboard closed. That also takes the controllers away from a VR game, so by
//     default it's off while a game (a scene app) runs: the screens stay up over the game,
//     the controllers stay in it, and the 3D mouse (its own laser mode) or the dashboard
//     works the screens. Modes: always, outside_games (default), dashboard (never on its
//     own; also for flatscreen games, which aren't scene apps).
//   - during a VR game the screens hide unless the dashboard is open (g_inGames, default),
//     or stay visible over it; the hotkey still shows them.
// OpenVR has no overlay-relative transforms here (openvr v2.15.6), so the bar, button,
// and handle are placed whenever their screen moves.
#include "vr.h"
#include "coords.h"

#include <openvr.h>

#include <fcntl.h>
#include <linux/input-event-codes.h>
#include <limits.h>
#include <spawn.h>

extern char **environ;  // for posix_spawn

#include <algorithm>
#include <chrono>
#include <array>
#include <cmath>
#include <cstdio>
#include <ctime>
#include <cstdlib>
#include <cstring>
#include <csignal>
#include <fcntl.h>
#include <initializer_list>
#include <limits.h>
#include <map>
#include <string>
#include <unistd.h>
#include <vector>

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
enum class Mode { Always, Dashboard, Gesture, Toggle };
enum class Lasers { Always, OutsideGames, Dashboard };
enum class InGames { Visible, Hide };

enum class GazeKind {
    None, Screen, Bar, Curve, Roll, Resize, Anchor, Slot, Instrument
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
int g_eyeLastErr = 0;             // last EVRInputError from GetEyeTrackingData*
int g_eyeFlags = 0;               // bit0=active bit1=valid bit2=tracked (last sample)
bool g_gazeDebug = false;
bool g_gazeFallbackHead = false;  // explicit debug fallback only — never silent
double g_gazeOrigin[3] = {}, g_gazeDir[3] = {0, 0, -1};
GazeTarget g_gazeTarget;
Clock::time_point g_lastGaze = Clock::now();

struct Screen {
    vr::VROverlayHandle_t overlay = vr::k_ulOverlayHandleInvalid, bar = vr::k_ulOverlayHandleInvalid,
                          handle = vr::k_ulOverlayHandleInvalid, curveButton = vr::k_ulOverlayHandleInvalid,
                          rollButton = vr::k_ulOverlayHandleInvalid,
                          anchorButton = vr::k_ulOverlayHandleInvalid;
    vr::VROverlayHandle_t slotButton[kSlotCount] = {};
    int width = 0, height = 0;    // DMA-BUF / OpenVR mouse scale (buffer pixels)
    int surfaceWidth = 0, surfaceHeight = 0;  // Wayland surface-local logical size
    double outputScale = 1.0;     // KWin output scale (Display Settings); for pointer seat map
    double metres = 1;
    double curve = 0;             // cylinder radius in metres; 0 = flat
    const void *shown = nullptr;  // a frame arrived
    bool visible = false;         // shown in VR right now
    // Attention-aware opacity: final = attentionResolved * visibilityFade.
    // Legacy single "opacity" maps to active=idle=X with attention off.
    float activeOpacity = 1.f;
    float idleOpacity = 1.f;
    float attentionResolved = 1.f;  // smoothed idle↔active
    float visibilityFade = 1.f;
    bool attentionEnabled = false;
    double attentionInMs = 150;     // fade toward active
    double attentionOutMs = 250;    // fade toward idle
    double attentionDwellMs = 80;   // gaze must stick before activating
    double attentionHoldMs = 150;   // stay active briefly after gaze leaves
    double attentionFocusMs = 0;    // time currently focused / unfocused accumulator
    bool attentionFocused = false;
    AnchorMode anchor = AnchorMode::World;
    vr::TrackedDeviceIndex_t pinned = kNone;  // rigid tracked-device pin only
    Mat pinRel = Identity();                  // reference/device -> screen
    Mat pose = Identity();                    // room pose (smoothed for soft follow)
    // Soft-follow dead zone: small head motion keeps a locked reference so you can
    // glance at a screen corner without the panel chasing. Past the threshold the
    // lock is pushed (excess only), so intentional turns still follow.
    bool followDeadzone = false;
    double followDeadzoneDeg = 15;            // head / yaw-follow
    double followDeadzoneM = 0.15;            // position-follow (+ head translation)
    bool followLockValid = false;
    Mat followLock = Identity();              // last soft-follow reference frame
    Drag drag = Drag::None;
    vr::TrackedDeviceIndex_t dragDevice = kNone;
    Mat dragRel = Identity();                 // device -> screen, while moving
    double grabX = 0, grabY = 0;              // resize: the grab point relative to the corner
    Mat rollFrom = Identity();                // roll: the pose at the press (pinRel when pinned)
    double rollAngle = 0;                     // roll: the laser's angle around the centre then
    bool hover[4] = {};                       // bar, curve, roll, resize
    bool hoverAnchor = false;
    bool hoverSlot[kSlotCount] = {};
    bool gazeHover = false;                   // any gaze hit on this screen or its chrome
    bool lasers = true;                       // MakeOverlaysInteractiveIfVisible is set
    float controls = 0;                       // the controls' fade, 0 (hidden) .. 1
    bool controlsUp = false;                  // the controls' overlays are shown
    long nearUntil = 0;                       // a laser was near the controls until this tick
    vr::TrackedDeviceIndex_t pinTarget = kNone;  // moving: rides on this device when let go
    vr::TrackedDeviceIndex_t onWrist = kNone;    // moving: the laser is in this controller's ring
    AnchorMode dragRestore = AnchorMode::World;  // soft/yaw/pos follow reapplied after a move
    bool barLit = false;
    double chrome = 0.3;          // the bar's width; the other controls follow it (ChromeSize)
    double grip = 0.04;           // the corner tab's and the round buttons' size
    double heightMetres() const { return width > 0 ? metres * height / width : metres * 9 / 16; }
    float ComposedAlpha() const { return attentionResolved * visibilityFade; }
    // chrome stays discoverable when the screen surface is fully transparent
    float ChromeAlpha() const {
        return std::max(ComposedAlpha(), controls > 0.02f ? kChromeFloor : 0.f);
    }
    std::vector<vr::VROverlayHandle_t> Controls() const {
        std::vector<vr::VROverlayHandle_t> out = {bar, curveButton, rollButton, handle, anchorButton};
        for (int i = 0; i < kSlotCount; ++i) out.push_back(slotButton[i]);
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

// --- Spatial Instruments (ambient VR info; not desktop surfaces) ---
enum class InstrumentType { Clock };

struct Instrument {
    std::string id;
    InstrumentType type = InstrumentType::Clock;
    bool enabled = false;
    vr::VROverlayHandle_t overlay = vr::k_ulOverlayHandleInvalid;
    vr::VROverlayHandle_t bar = vr::k_ulOverlayHandleInvalid;
    double metres = 0.35;
    float activeOpacity = 1.f;
    float idleOpacity = 0.35f;
    float attentionResolved = 1.f;
    bool attentionEnabled = true;
    double attentionInMs = 150;
    double attentionOutMs = 250;
    double attentionDwellMs = 80;
    double attentionHoldMs = 150;
    double attentionFocusMs = 0;
    bool attentionFocused = false;
    AnchorMode anchor = AnchorMode::World;
    vr::TrackedDeviceIndex_t pinned = kNone;
    Mat pinRel = Identity();
    Mat pose = Identity();
    bool followDeadzone = false;
    double followDeadzoneDeg = 15;
    double followDeadzoneM = 0.15;
    bool followLockValid = false;
    Mat followLock = Identity();
    Drag drag = Drag::None;
    vr::TrackedDeviceIndex_t dragDevice = kNone;
    Mat dragRel = Identity();
    AnchorMode dragRestore = AnchorMode::World;
    bool hoverBar = false;
    bool barLit = false;
    float controls = 0;
    bool controlsUp = false;
    long nearUntil = 0;
    bool gazeHover = false;
    bool visible = false;
    int lastMinute = -1;
    int texW = 384, texH = 128;
    std::vector<uint8_t> pixels;
    double heightMetres() const { return metres * double(texH) / double(texW); }
    float ComposedAlpha() const { return attentionResolved; }
};

std::vector<Instrument> g_instruments;

bool InstrumentPose(const Instrument &inst, Mat *out);
void UpdateInstrumentAttention(double dt);
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
bool g_gameRunning = false;              // a scene app (VR game) is running
InGames g_inGames = InGames::Hide;       // during a VR game, the always mode acts like the dashboard mode

// ---------------------------------------------------------------- chrome (bar, button, handle)

// The controls look like SteamVR's own: a light translucent pill for the bar, dark
// translucent discs with white glyphs for the buttons (the overlay alpha, kChromeIdle,
// dims them further until a laser is on them).
std::vector<uint8_t> PillTexture(int w, int h, uint8_t red, uint8_t green, uint8_t blue, uint8_t alpha) {
    std::vector<uint8_t> px(size_t(w) * h * 4, 0);
    const double r = h / 2.0 - 1;
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x) {
            const double cx = std::clamp(double(x), r + 1, w - r - 1), cy = h / 2.0;
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

vr::VROverlayHandle_t MakeChrome(const char *key, const char *name, const std::vector<uint8_t> &px, int w, int h) {
    vr::VROverlayHandle_t o = vr::k_ulOverlayHandleInvalid;
    if (vr::VROverlay()->CreateOverlay(key, name, &o) != vr::VROverlayError_None) return o;
    vr::VROverlay()->SetOverlayRaw(o, const_cast<uint8_t *>(px.data()), uint32_t(w), uint32_t(h), 4);
    vr::VROverlay()->SetOverlayInputMethod(o, vr::VROverlayInputMethod_Mouse);
    vr::VROverlay()->SetOverlaySortOrder(o, 10);
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

// Bottom strip: bar / curve / roll / resize / anchor / slots.
std::vector<Mat> ControlOffsets(const Screen &s) {
    const double h = s.heightMetres(), bar = s.chrome, button = s.grip, gap = bar * 0.06;
    std::vector<Mat> out;
    out.push_back(BarOffset(s));
    out.push_back(OnSurface(s, bar / 2 + gap + button / 2, BarY(s), 0.003));
    out.push_back(OnSurface(s, bar / 2 + gap * 2 + button * 1.5, BarY(s), 0.003));
    out.push_back(OnSurface(s, s.metres / 2 + s.grip / 2, -(h / 2 + s.grip / 2), 0.003));
    out.push_back(OnSurface(s, -(bar / 2 + gap + button / 2), BarY(s), 0.003));
    for (int i = 0; i < kSlotCount; ++i) {
        // Left → right: slots 1..6 (i=0 furthest left).
        const double x = -(bar / 2 + gap * 2 + button * 1.5 + (kSlotCount - 1 - i) * (button + gap));
        out.push_back(OnSurface(s, x, BarY(s), 0.003));
    }
    return out;
}

void PlaceChrome(Screen &s) {
    ChromeSize(s);
    const double bar = s.chrome, button = s.grip;
    const auto offsets = ControlOffsets(s);
    vr::VROverlay()->SetOverlayWidthInMeters(s.bar, float(bar));
    vr::VROverlay()->SetOverlayWidthInMeters(s.curveButton, float(button));
    vr::VROverlay()->SetOverlayWidthInMeters(s.rollButton, float(button));
    vr::VROverlay()->SetOverlayWidthInMeters(s.handle, float(s.grip));
    vr::VROverlay()->SetOverlayWidthInMeters(s.anchorButton, float(button));
    for (int i = 0; i < kSlotCount; ++i)
        vr::VROverlay()->SetOverlayWidthInMeters(s.slotButton[i], float(button));
    vr::VROverlay()->SetOverlayCurvature(s.bar, s.curve > 0 ? float(std::min(1.0, bar / (2 * M_PI * s.curve))) : 0.f);
    auto controls = s.Controls();
    if (s.pinned != kNone) {
        for (size_t i = 0; i < controls.size() && i < offsets.size(); ++i) {
            const Mat m = Mul(s.pinRel, offsets[i]);
            vr::VROverlay()->SetOverlayTransformTrackedDeviceRelative(controls[i], s.pinned, &m);
        }
        return;
    }
    Mat p;
    if (!ScreenPose(s, &p)) return;
    for (size_t i = 0; i < controls.size() && i < offsets.size(); ++i) {
        const Mat m = Mul(p, offsets[i]);
        vr::VROverlay()->SetOverlayTransformAbsolute(controls[i], vr::TrackingUniverseStanding, &m);
    }
}

void SetAbsolute(Screen &s, const Mat &pose) {
    s.anchor = AnchorMode::World;
    s.pinned = kNone;
    s.pose = pose;
    vr::VROverlay()->SetOverlayTransformAbsolute(s.overlay, vr::TrackingUniverseStanding, &pose);
    PlaceChrome(s);
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
    for (int i = 0; i < kSlotCount; ++i) {
        if (s.slotButton[i] == vr::k_ulOverlayHandleInvalid) continue;
        const bool lit = (i + 1) == g_currentSlot;
        auto px = DigitTexture(64, i + 1, lit);
        vr::VROverlay()->SetOverlayRaw(s.slotButton[i], px.data(), 64, 64, 4);
    }
    if (s.anchorButton != vr::k_ulOverlayHandleInvalid) {
        auto px = AnchorTexture(64, s.anchor);
        vr::VROverlay()->SetOverlayRaw(s.anchorButton, px.data(), 64, 64, 4);
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
        const Mat cur = ReferenceFrame(s.anchor, hmd);
        Mat ref = cur;
        if (s.followDeadzone) {
            if (!s.followLockValid) {
                s.followLock = cur;
                s.followLockValid = true;
            }
            PushFollowLock(&s.followLock, cur, s.anchor, s.followDeadzoneDeg, s.followDeadzoneM);
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
// The mode in effect: during a VR game (with g_inGames Hide), "always" becomes "only with
// the dashboard open", so the screens stay out of the game until you open the dashboard.
Mode EffectiveMode() {
    return g_gameRunning && g_inGames == InGames::Hide && g_mode == Mode::Always ? Mode::Dashboard : g_mode;
}

// A VR game starting or stopping (checked twice a second) resets the hide/show switch, whose
// meaning depends on the mode in effect.
void UpdateGame() {
    if (g_tick % 45) return;
    const bool running = vr::VRApplications()->GetCurrentSceneProcessId() != 0;
    if (running == g_gameRunning) return;
    g_gameRunning = running;
    g_manual = false;
    std::printf("%s\n", running ? "a VR game started" : "the VR game ended");
}

bool ModeVisible() {
    switch (EffectiveMode()) {
        case Mode::Always: return !g_manual;
        case Mode::Toggle: return g_manual;
        case Mode::Dashboard: return g_manual || vr::VROverlay()->IsDashboardVisible();
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
        else if (k >= 5 && k < 5 + kSlotCount) {
            active = s.hoverSlot[k - 5] ||
                     (g_gazeTarget.kind == GazeKind::Slot && g_gazeTarget.slot == int(k - 5) && s.gazeHover);
            fill = g_slotFilled[k - 5] ? 1.f : 0.35f;
            if (g_currentSlot == int(k - 5) + 1) fill = std::max(fill, 1.f);
        }
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
        return;
    }
    // Hidden: the controls go at once (UpdateControls brings them back).
    vr::VROverlay()->HideOverlay(s.overlay);
    for (auto o : s.Controls()) vr::VROverlay()->HideOverlay(o);
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
        bool slotHit = false;
        for (int i = 0; i < kSlotCount; ++i) {
            const double sx = -(bar / 2 + gap * 2 + button * 1.5 + (kSlotCount - 1 - i) * (button + gap));
            if (RayHitsLocalBox(hx, hy, sx, by, button / 2, button / 2)) {
                consider(GazeKind::Slot, i, dist);
                slotHit = true;
                break;
            }
        }
        if (slotHit) continue;
        // Screen surface.
        if (std::fabs(hx) <= halfW && std::fabs(hy) <= halfH) consider(GazeKind::Screen, -1, dist);
    }
    for (size_t ii = 0; ii < g_instruments.size(); ++ii) {
        Instrument &inst = g_instruments[ii];
        if (!inst.enabled || !inst.visible) continue;
        Mat ip;
        if (!InstrumentPose(inst, &ip)) continue;
        double hx, hy;
        if (!RayOnPlane(ip, ray, &hx, &hy)) continue;
        const double halfW = inst.metres / 2, halfH = inst.heightMetres() / 2;
        if (std::fabs(hx) > halfW * 1.1 || std::fabs(hy) > halfH * 1.25) continue;
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
    return best;
}

void UpdateGaze(double dt) {
    (void)dt;
    for (auto &[i, s] : g_screens) s.gazeHover = false;
    for (auto &inst : g_instruments) inst.gazeHover = false;
    double origin[3], dir[3];
    bool got = SampleEyeGaze(origin, dir);
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
            default: break;
        }
        std::printf("gaze: eye=%s valid=%s target=%s screen=%d u=%.3f v=%.3f dist=%.3f\n",
                    g_eyeAvailable ? "yes" : "no", g_eyeValid ? "yes" : (g_gazeFallbackHead ? "fallback" : "no"),
                    kind, g_gazeTarget.screen + 1, g_gazeTarget.u, g_gazeTarget.v, g_gazeTarget.distance);
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
            const bool hit =
                g_gazeTarget && g_gazeTarget.screen == index &&
                (g_gazeTarget.kind == GazeKind::Screen || g_gazeTarget.kind == GazeKind::Bar ||
                 g_gazeTarget.kind == GazeKind::Curve || g_gazeTarget.kind == GazeKind::Roll ||
                 g_gazeTarget.kind == GazeKind::Resize ||
                 g_gazeTarget.kind == GazeKind::Anchor || g_gazeTarget.kind == GazeKind::Slot);
            // Temporary invalid sample: ease toward idle, do not slam.
            const bool valid = g_eyeValid || (g_gazeFallbackHead && g_gazeTarget);
            if (!valid) {
                const double tau = s.attentionOutMs / 1000.0;
                const double a = tau <= 1e-4 ? 1.0 : 1.0 - std::exp(-dt / tau);
                s.attentionResolved = float(s.attentionResolved + (s.idleOpacity - s.attentionResolved) * a);
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
    if (!s.attentionEnabled || (!g_eyeAvailable && !g_gazeFallbackHead))
        s.attentionResolved = s.activeOpacity;
    else
        s.attentionResolved = std::clamp(s.attentionResolved, std::min(s.idleOpacity, s.activeOpacity),
                                         std::max(s.idleOpacity, s.activeOpacity));
    PlaceChrome(s);
    ApplyAlpha(s);
}

void UpdateVisibility() {
    const bool shared = ModeVisible();
    Mat head;
    const bool haveHead = DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head);
    for (auto &[i, s] : g_screens) {
        bool visible = s.shown && (shared || s.drag != Drag::None);
        float visFade = 1;
        Mat p;
        // Wrist fade is only for controller-pinned screens.
        if (visible && s.pinned != kNone && IsHandController(s.pinned) && s.drag == Drag::None && haveHead &&
            ScreenPose(s, &p)) {
            const double a = FacingAngle(p, head);
            visFade = float(std::clamp((g_wristAngle - a) / kFade, 0.0, 1.0));
            visible = visFade > 0.02f;
        }
        // Keep chrome interactable even when the surface is fully transparent.
        if (!visible && s.shown && s.controls > 0.02f) visible = true, visFade = 0.f;
        SetVisible(s, visible, visFade);
    }
}


// Controllers' lasers on the screens (see the top): the flag follows the mode and whether a
// VR game runs.
void UpdateLasers() {
    const bool want = g_lasers == Lasers::Always || (g_lasers == Lasers::OutsideGames && !g_gameRunning);
    for (auto &[i, s] : g_screens) {
        if (s.lasers == want) continue;
        s.lasers = want;
        vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_MakeOverlaysInteractiveIfVisible, want);
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
        bool anyHover = s.hover[0] || s.hover[1] || s.hover[2] || s.hover[3] || s.hoverAnchor;
        for (int i = 0; i < kSlotCount; ++i) anyHover = anyHover || s.hoverSlot[i];
        // Gaze drives attention fade only — chrome reveal stays laser / 3D-mouse.
        const bool inUse = s.drag != Drag::None || anyHover;
        const bool want = s.visible && (inUse || g_tick < s.nearUntil);
        // The controls stay shown while their screen is, just fully transparent when not
        // wanted: SteamVR's laser still hits them, and the hover event brings them in, for
        // any device's laser, whatever its shape.
        if (s.visible && !s.controlsUp) {
            for (auto o : s.Controls()) vr::VROverlay()->ShowOverlay(o);
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

// Let go: pin to the armed wrist, as the screen is now.
void FinishDrag(Screen &s, int index) {
    const bool moved = s.drag == Drag::Move;
    const vr::TrackedDeviceIndex_t target = s.pinTarget;
    const AnchorMode restore = s.dragRestore;
    EndDrag(s);
    s.dragRestore = AnchorMode::World;
    Mat c, p;
    if (!moved) return;
    ArrangeDesktopSoon();
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
    for (auto &[index, s] : g_screens)
        if (s.drag != Drag::None && s.dragDevice == dev) FinishDrag(s, index);
    EndInstrumentDragsBy(dev);
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

Instrument &FindOrCreateClock() {
    if (Instrument *existing = FindInstrument("clock")) return *existing;
    Instrument inst;
    inst.id = "clock";
    inst.type = InstrumentType::Clock;
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
        const Mat cur = ReferenceFrame(inst.anchor, hmd);
        Mat ref = cur;
        if (inst.followDeadzone) {
            if (!inst.followLockValid) {
                inst.followLock = cur;
                inst.followLockValid = true;
            }
            PushFollowLock(&inst.followLock, cur, inst.anchor, inst.followDeadzoneDeg, inst.followDeadzoneM);
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
            FillInstrumentRect(inst.pixels, w, h, cx, oy + dh / 3 - 4, cx + 8, oy + dh / 3 + 4, 235, 240, 245, 230);
            FillInstrumentRect(inst.pixels, w, h, cx, oy + 2 * dh / 3 - 4, cx + 8, oy + 2 * dh / 3 + 4, 235, 240, 245,
                               230);
            ox += 18;
        }
        DrawSegDigit(inst.pixels, w, h, ox, oy, dw, dh, digits[i], 235, 240, 245, 230);
        ox += dw + gap;
    }
    SoftOutlineInstrument(inst.pixels, w, h);
    if (inst.overlay != vr::k_ulOverlayHandleInvalid)
        vr::VROverlay()->SetOverlayRaw(inst.overlay, inst.pixels.data(), uint32_t(w), uint32_t(h), 4);
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
    if (vr::VROverlay()->CreateOverlay(key, name, &inst.overlay) != vr::VROverlayError_None) {
        std::fprintf(stderr, "openvr: can't create instrument overlay %s\n", key);
        return;
    }
    vr::VROverlay()->SetOverlayWidthInMeters(inst.overlay, float(inst.metres));
    vr::VROverlay()->SetOverlayInputMethod(inst.overlay, vr::VROverlayInputMethod_None);
    // Content is non-interactive; keep texture alpha (no IgnoreTextureAlpha).
    // Do not set MakeOverlaysInteractiveIfVisible on the content overlay.
    std::snprintf(key, sizeof key, "frametop.instrument.%s.bar", inst.id.c_str());
    std::snprintf(name, sizeof name, "Instrument %s: move", inst.id.c_str());
    inst.bar = MakeChrome(key, name, BarTexture(false), 256, 24);
    if (inst.bar != vr::k_ulOverlayHandleInvalid) {
        vr::VROverlay()->SetOverlayFlag(inst.bar, vr::VROverlayFlags_MakeOverlaysInteractiveIfVisible, true);
        vr::VROverlay()->SetOverlayFlag(inst.bar, vr::VROverlayFlags_SendVRDiscreteScrollEvents, true);
    }
    inst.attentionResolved = inst.activeOpacity;
    RefreshClockTexture(inst, true);
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
            const bool valid = g_eyeValid || (g_gazeFallbackHead && g_gazeTarget);
            if (!valid) {
                const double tau = inst.attentionOutMs / 1000.0;
                const double a = tau <= 1e-4 ? 1.0 : 1.0 - std::exp(-dt / tau);
                inst.attentionResolved =
                    float(inst.attentionResolved + (inst.idleOpacity - inst.attentionResolved) * a);
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
            const Mat bar = Mul(p, InstrumentBarOffset(inst));
            const double chrome = std::max(0.04, inst.metres * 0.18);
            const double reach = std::max(chrome * 0.5, 0.03);
            std::vector<Mat> spots;
            for (double f : {-0.5, -0.25, 0.0, 0.25, 0.5})
                spots.push_back(Mul(bar, Translation(f * chrome, 0, 0)));
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
        if (inst.visible && !inst.controlsUp && inst.bar != vr::k_ulOverlayHandleInvalid) {
            vr::VROverlay()->ShowOverlay(inst.bar);
            inst.controlsUp = true;
            ApplyInstrumentAlpha(inst);
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
    if (!inst.attentionEnabled || (!g_eyeAvailable && !g_gazeFallbackHead))
        inst.attentionResolved = inst.activeOpacity;
    else
        inst.attentionResolved = std::clamp(inst.attentionResolved, std::min(inst.idleOpacity, inst.activeOpacity),
                                            std::max(inst.idleOpacity, inst.activeOpacity));
    ApplyInstrumentAlpha(inst);
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
    }
    return "clock";
}

void TickInstruments(double dt) {
    for (auto &inst : g_instruments) {
        if (!inst.enabled) continue;
        RefreshClockTexture(inst, false);
        ShowInstrument(inst, true);
    }
    UpdateInstrumentFollow(dt);
    UpdateInstrumentControls();
    PollInstrumentBars();
}



}  // namespace

extern "C" {

bool ft_vr_init(void) {
    vr::EVRInitError err = vr::VRInitError_None;
    vr::VR_Init(&err, vr::VRApplication_Overlay);
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
    return true;
}

void ft_vr_shutdown(void) {
    ClearInstruments();
    for (auto &[i, s] : g_screens)
        for (auto o : s.All()) vr::VROverlay()->DestroyOverlay(o);
    for (auto &[dev, g] : g_guides)
        for (auto o : {g.ring.overlay, g.dot.overlay}) vr::VROverlay()->DestroyOverlay(o);
    for (auto &[k, h] : g_imports) vr::VRIPCResourceManager()->UnrefResource(h);
    g_guides.clear();
    g_screens.clear();
    g_imports.clear();
    vr::VR_Shutdown();
}

int ft_vr_modifiers(uint32_t format, uint64_t *out, int max) {
    uint32_t n = uint32_t(max);
    if (!vr::VRIPCResourceManager()->GetDmabufModifiers(vr::VRApplication_Overlay, format, &n, out)) return 0;
    return int(n < uint32_t(max) ? n : uint32_t(max));
}

bool ft_vr_screens_shown(void) { return ModeVisible(); }

void ft_vr_screen_create(int index, double metres, int count) {
    Screen &s = g_screens[index];
    s.metres = metres;
    char key[64], name[64];
    std::snprintf(key, sizeof key, "frametop.screen.%d", index + 1);
    std::snprintf(name, sizeof name, "Screen %d", index + 1);
    if (vr::VROverlay()->CreateOverlay(key, name, &s.overlay) != vr::VROverlayError_None) {
        std::fprintf(stderr, "openvr: can't create overlay %s\n", key);
        return;
    }
    vr::VROverlay()->SetOverlayWidthInMeters(s.overlay, float(metres));
    vr::VROverlay()->SetOverlayInputMethod(s.overlay, vr::VROverlayInputMethod_Mouse);
    vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_IgnoreTextureAlpha, true);
    vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_SendVRDiscreteScrollEvents, true);
    vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_MakeOverlaysInteractiveIfVisible, true);
    static const auto corner = CornerTexture(64);
    static const auto curve = CurveTexture(64);
    static const auto roll = RollTexture(64);
    std::snprintf(key, sizeof key, "frametop.screen.%d.bar", index + 1);
    std::snprintf(name, sizeof name, "Screen %d: move", index + 1);
    s.bar = MakeChrome(key, name, BarTexture(false), 256, 24);
    vr::VROverlay()->SetOverlayFlag(s.bar, vr::VROverlayFlags_SendVRDiscreteScrollEvents, true);
    std::snprintf(key, sizeof key, "frametop.screen.%d.curve", index + 1);
    std::snprintf(name, sizeof name, "Screen %d: curve", index + 1);
    s.curveButton = MakeChrome(key, name, curve, 64, 64);
    std::snprintf(key, sizeof key, "frametop.screen.%d.roll", index + 1);
    std::snprintf(name, sizeof name, "Screen %d: roll", index + 1);
    s.rollButton = MakeChrome(key, name, roll, 64, 64);
    vr::VROverlay()->SetOverlayFlag(s.rollButton, vr::VROverlayFlags_SendVRDiscreteScrollEvents, true);
    std::snprintf(key, sizeof key, "frametop.screen.%d.resize", index + 1);
    std::snprintf(name, sizeof name, "Screen %d: resize", index + 1);
    s.handle = MakeChrome(key, name, corner, 64, 64);
    std::snprintf(key, sizeof key, "frametop.screen.%d.anchor", index + 1);
    std::snprintf(name, sizeof name, "Screen %d: anchor", index + 1);
    s.anchorButton = MakeChrome(key, name, AnchorTexture(64, AnchorMode::World), 64, 64);
    for (int i = 0; i < kSlotCount; ++i) {
        std::snprintf(key, sizeof key, "frametop.screen.%d.slot%d", index + 1, i + 1);
        std::snprintf(name, sizeof name, "Screen %d: profile %d", index + 1, i + 1);
        s.slotButton[i] = MakeChrome(key, name, DigitTexture(64, i + 1, false), 64, 64);
    }
    s.attentionResolved = s.activeOpacity;
    ApplyAlpha(s);
    // Until the layout places it: 2 m ahead of the head, in a row, screen 1 on the left.
    RefreshPoses();
    Mat head;
    if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head)) head = Identity();
    const double heading = std::atan2(head.m[0][2], head.m[2][2]) * 180 / M_PI;
    const double yaw = heading + (double(count - 1) / 2 - index) * 35;
    const double dx = -std::sin(yaw * M_PI / 180), dz = -std::cos(yaw * M_PI / 180);
    SetAbsolute(s, PanelPose(head.m[0][3] + dx * 2, head.m[1][3], head.m[2][3] + dz * 2, yaw, 0, 0));
}

void ft_vr_screen_destroy(int index) {
    auto it = g_screens.find(index);
    if (it == g_screens.end()) return;
    for (auto o : it->second.All()) vr::VROverlay()->DestroyOverlay(o);
    g_screens.erase(it);
}

bool ft_vr_screen_present(int index, const void *key, const struct ft_dmabuf *b) {
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
        // Mouse scale stays in *buffer* pixels; seat events map via ft_buffer_to_surface.
        vr::HmdVector2_t scale = {float(s.width), float(s.height)};
        vr::VROverlay()->SetOverlayMouseScale(s.overlay, &scale);
        PlaceChrome(s);  // the height changed
        std::printf("screen %d: buffer %dx%d (surface %dx%d)\n", index + 1, s.width, s.height, s.surfaceWidth,
                    s.surfaceHeight);
    }
    vr::SharedTextureHandle_t handle = it->second;
    vr::Texture_t tex = {&handle, vr::TextureType_SharedTextureHandle, vr::ColorSpace_Gamma};
    vr::VROverlay()->SetOverlayTexture(s.overlay, &tex);
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
    auto it = g_imports.find(key);
    if (it == g_imports.end()) return;
    vr::VRIPCResourceManager()->UnrefResource(it->second);
    g_imports.erase(it);
}

void ft_vr_poll(void (*handle)(const struct ft_event *, void *), void *data) {
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
        // The screen itself: input for KWin.
        while (vr::VROverlay()->PollNextOverlayEvent(s.overlay, &ev, sizeof ev)) {
            ft_event e{};
            e.screen = index;
            switch (ev.eventType) {
                case vr::VREvent_MouseMove:
                case vr::VREvent_MouseButtonDown:
                case vr::VREvent_MouseButtonUp: {
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
                    } else {
                        if (ev.eventType == vr::VREvent_MouseButtonUp) EndDragsBy(ev.trackedDeviceIndex);
                        e.type = FT_BUTTON;
                        e.button = LinuxButton(ev.data.mouse.button);
                        e.pressed = ev.eventType == vr::VREvent_MouseButtonDown;
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
                    e.type = FT_LEAVE;
                    break;
                default:
                    continue;
            }
            handle(&e, data);
        }
        // The controls light up under a laser.
        auto hover = [&](int k) {
            const bool on = ev.eventType == vr::VREvent_MouseMove || ev.eventType == vr::VREvent_FocusEnter;
            if (!on && ev.eventType != vr::VREvent_FocusLeave) return;
            if (s.hover[k] != on) s.hover[k] = on, ApplyAlpha(s);
        };
        // The bar: move (and push/pull with the wheel while moving).
        while (vr::VROverlay()->PollNextOverlayEvent(s.bar, &ev, sizeof ev)) {
            hover(0);
            if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                StartDrag(s, Drag::Move, ev.trackedDeviceIndex);
            else if (ev.eventType == vr::VREvent_MouseButtonUp)
                EndDragsBy(ev.trackedDeviceIndex);
            else if (ev.eventType == vr::VREvent_ScrollDiscrete && s.drag == Drag::Move)
                Push(s, ev.data.scroll.ydelta);
        }
        // The corner: resize.
        while (vr::VROverlay()->PollNextOverlayEvent(s.handle, &ev, sizeof ev)) {
            hover(3);
            if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                StartDrag(s, Drag::Resize, ev.trackedDeviceIndex);
            else if (ev.eventType == vr::VREvent_MouseButtonUp)
                EndDragsBy(ev.trackedDeviceIndex);
        }
        // The curve button.
        while (vr::VROverlay()->PollNextOverlayEvent(s.curveButton, &ev, sizeof ev)) {
            hover(1);
            if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                ToggleCurve(s);
            else if (ev.eventType == vr::VREvent_MouseButtonUp)
                EndDragsBy(ev.trackedDeviceIndex);
        }
        // The roll button: drag around like a knob, or scroll.
        while (vr::VROverlay()->PollNextOverlayEvent(s.rollButton, &ev, sizeof ev)) {
            hover(2);
            if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                StartDrag(s, Drag::Roll, ev.trackedDeviceIndex);
            else if (ev.eventType == vr::VREvent_MouseButtonUp)
                EndDragsBy(ev.trackedDeviceIndex);
            else if (ev.eventType == vr::VREvent_ScrollDiscrete && s.drag == Drag::None) {
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
        while (vr::VROverlay()->PollNextOverlayEvent(s.anchorButton, &ev, sizeof ev)) {
            hoverExtra(&s.hoverAnchor);
            if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left)
                CycleScreenAnchor(s);
        }
        for (int si = 0; si < kSlotCount; ++si) {
            while (vr::VROverlay()->PollNextOverlayEvent(s.slotButton[si], &ev, sizeof ev)) {
                hoverExtra(&s.hoverSlot[si]);
                if (ev.eventType == vr::VREvent_MouseButtonDown && ev.data.mouse.button == vr::VRMouseButton_Left) {
                    if (!g_slotFilled[si]) continue;
                    char slot[24];
                    std::snprintf(slot, sizeof slot, "profile.slot.%d", si + 1);
                    SpawnLayoutAsync({"action", slot});
                }
            }
        }
        if (s.drag != Drag::None) UpdateDrag(s, index);
    }
    RefreshChrome();
    vr::VREvent_t ev;
    while (vr::VRSystem()->PollNextEvent(&ev, sizeof ev)) {
        if (ev.eventType == vr::VREvent_Quit) {
            ft_event e{};
            e.type = FT_QUIT;
            handle(&e, data);
        } else if (ev.eventType == vr::VREvent_TrackedDeviceDeactivated) {
            EndDragsBy(ev.trackedDeviceIndex);
        }
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
}

// Future pinch / finger tracking should call these (gaze selects; pinch confirms). Not wired yet.
//   activateCurrentGazeTarget()  — chrome → semantic action; screen → desktop click at UV
//   beginGazeDrag() / updateGazeDrag(delta) / endGazeDrag()
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
//   controllers always|outside_games|dashboard   when controllers' lasers work the screens
//   ingames hide|visible      during a VR game, "always" acts like "only with the dashboard"
//                             (hide), or stays as it is (visible)
//   state         -> "ok <mode> <manual 0|1> <wrist deg> <gesture hand> <gesture deg>
//                     <controllers> <game running 0|1> <ingames>"
// (size <screen> <w> <h> and key <code> <value> are handled in compositor.c.) Screens are
// numbered from 1 here, like everywhere the user sees them.
void ft_vr_command(const char *cmd, char *reply, int size) {
    RefreshPoses();
    int n;
    double x, y, z, yaw, pitch, roll, w;
    char word[16], hand[32], filled[64];
    float r[12];
    auto each = [&](const char *which, auto fn) -> bool {  // "all" or a screen number
        if (std::strcmp(which, "all") == 0) {
            for (auto &[i, s] : g_screens) fn(s);
            return true;
        }
        Screen *s = Find(std::atoi(which));
        if (s) fn(*s);
        return s != nullptr;
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
                          "ok eye=%d valid=%d fallback=%d err=%d flags=%d origin=%.4f,%.4f,%.4f dir=%.4f,%.4f,%.4f "
                          "target=%s screen=%d slot=%d u=%.4f v=%.4f pixel=%d,%d buffer_pixel=%d,%d "
                          "surface=%dx%d buffer=%dx%d dist=%.4f",
                          g_eyeAvailable ? 1 : 0, g_eyeValid ? 1 : 0, g_gazeFallbackHead ? 1 : 0, g_eyeLastErr,
                          g_eyeFlags, g_gazeOrigin[0], g_gazeOrigin[1], g_gazeOrigin[2], g_gazeDir[0], g_gazeDir[1],
                          g_gazeDir[2], kind, g_gazeTarget.screen + 1, g_gazeTarget.slot + 1, g_gazeTarget.u,
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
            std::snprintf(reply, size, "error gaze state|debug on|debug off|fallback head|fallback off");
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
        int len = std::snprintf(reply, size, "ok %zu", g_screens.size());
        for (auto &[i, s] : g_screens)
            if (len < size)
                len += std::snprintf(reply + len, size - len, " %d:%dx%d:%.3f", i + 1, s.width, s.height, s.metres);
    } else if (std::strncmp(cmd, "head", 4) == 0) {
        Mat m;
        if (!DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &m))
            return (void)std::snprintf(reply, size, "error no head pose (headset off?)");
        std::snprintf(reply, size, "ok %.4f %.4f %.4f %.2f", m.m[0][3], m.m[1][3], m.m[2][3],
                      std::atan2(m.m[0][2], m.m[2][2]) * 180 / M_PI);
    } else if (std::sscanf(cmd, "visibility %15s", word) == 1) {
        const std::string m = word;
        if (m == "always") g_mode = Mode::Always;
        else if (m == "dashboard") g_mode = Mode::Dashboard;
        else if (m == "gesture") g_mode = Mode::Gesture;
        else if (m == "toggle") g_mode = Mode::Toggle;
        else return (void)std::snprintf(reply, size, "error modes: always dashboard gesture toggle");
        g_manual = false;
        std::snprintf(reply, size, "ok %s", ModeName());
    } else if (std::sscanf(cmd, "wrist %lf", &w) == 1) {
        g_wristAngle = std::clamp(w, 10.0, 180.0);
        std::snprintf(reply, size, "ok");
    } else if (std::sscanf(cmd, "gesture %15s %lf", hand, &w) == 2) {
        g_gestureHand = std::strcmp(hand, "right") == 0 ? "right" : "left";
        g_gestureAngle = std::clamp(w, 5.0, 90.0);
        std::snprintf(reply, size, "ok");
    } else if (!std::strncmp(cmd, "hide", 4) || !std::strncmp(cmd, "show", 4) || !std::strncmp(cmd, "toggle", 6)) {
        const bool always = EffectiveMode() == Mode::Always;
        const bool shownNow = always ? !g_manual : g_manual;
        const bool want = cmd[0] == 's' ? true : cmd[0] == 'h' ? false : !shownNow;
        g_manual = always ? !want : want;
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
    } else if (std::strncmp(cmd, "state", 5) == 0) {
        std::snprintf(reply, size, "ok %s %d %.0f %s %.0f %s %d %s", ModeName(), g_manual ? 1 : 0, g_wristAngle,
                      g_gestureHand.c_str(), g_gestureAngle, LasersName(), g_gameRunning ? 1 : 0,
                      g_inGames == InGames::Hide ? "hide" : "visible");
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
            if (std::strcmp(id, "clock") != 0 && !FindInstrument(id))
                return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
            Instrument &inst = FindOrCreateClock();  // v1: clock only
            EnableInstrument(inst, true);
            if (IsIdentityMat(inst.pose)) RecenterInstrument(inst);
            std::snprintf(reply, size, "ok");
        } else if (std::sscanf(rest, "disable %63s", id) == 1) {
            Instrument *inst = FindInstrument(id);
            if (!inst) return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
            EnableInstrument(*inst, false);
            std::snprintf(reply, size, "ok");
        } else if (std::sscanf(rest, "recenter %63s", id) == 1) {
            if (std::strcmp(id, "clock") != 0 && !FindInstrument(id))
                return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
            Instrument &inst = FindOrCreateClock();
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
                if (std::strcmp(id, "clock") != 0)
                    return (void)std::snprintf(reply, size, "error unknown instrument %s", id);
                inst = &FindOrCreateClock();
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
        } else {
            std::snprintf(reply, size, "error instrument commands: list|get|enable|disable|place|width|pin|unpin|"
                                       "opacity|attention|recenter|clear");
        }
    } else {
        std::snprintf(reply, size, "error unknown command");
    }
}

}  // extern "C"
