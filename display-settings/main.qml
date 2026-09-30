// Frametop Display Settings (Kirigami). Backend: ft_display_settings.py ("backend").
import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root
    title: "Frametop Display Settings"
    width: Kirigami.Units.gridUnit * 46
    height: Kirigami.Units.gridUnit * 36

    // Pages as tabs across the top (a side drawer was easy to miss).
    readonly property var pages: backend.backend === "screens"
        ? [{ text: "Screens", icon: "video-display", page: screensPage },
           { text: "Layout", icon: "view-grid", page: layoutPage },
           { text: "Visibility", icon: "view-visible", page: visibilityPage },
           { text: "Background", icon: "wallpaper", page: backgroundPage },
           { text: "Spatial Instruments", icon: "clock", page: instrumentsPage }]
        : [{ text: "Screens", icon: "video-display", page: screensPage },
           { text: "Layout", icon: "view-grid", page: layoutPage },
           { text: "Background", icon: "wallpaper", page: backgroundPage }]

    header: Controls.TabBar {
        id: tabs
        Repeater {
            model: root.pages
            Controls.TabButton {
                required property var modelData
                text: modelData.text
                icon.name: modelData.icon
                onClicked: root.show(modelData.page)
            }
        }
        Component.onCompleted: currentIndex = ({
            layout: 1,
            visibility: backend.backend === "screens" ? 2 : 0,
            background: backend.backend === "screens" ? 3 : 2,
            instruments: backend.backend === "screens" ? 4 : 0
        })[startPage] || 0
    }

    function show(page) {
        pageStack.clear()
        pageStack.push(page)
    }

    // FT_DISPLAY_PAGE=layout|visibility|instruments|background opens the app on that page.
    pageStack.initialPage: ({ layout: layoutPage, visibility: visibilityPage,
                              instruments: instrumentsPage, background: backgroundPage })[startPage] || screensPage

    Connections {
        target: backend
        function onMessage(text, isError) {
            root.showPassiveNotification(text, isError ? "long" : "short")
        }
    }

    Kirigami.PromptDialog {
        id: restartDialog
        title: "Restart the desktop?"
        subtitle: "Every window on the desktop closes, this app too. It starts again with the current settings."
        standardButtons: Kirigami.Dialog.NoButton
        customFooterActions: [
            Kirigami.Action {
                text: "Restart"
                icon.name: "view-refresh"
                onTriggered: { restartDialog.close(); backend.restartDesktop() }
            },
            Kirigami.Action {
                text: "Cancel"
                icon.name: "dialog-cancel"
                onTriggered: restartDialog.close()
            }
        ]
    }

    // ---------------------------------------------------------------- Screens
    Component {
        id: screensPage
        Kirigami.ScrollablePage {
            id: spage
            title: "Screens"
            property bool md: backend.backend === "screens"

            actions: [
                Kirigami.Action {
                    visible: spage.md
                    text: "Add screen"
                    icon.name: "list-add"
                    onTriggered: backend.addScreen()
                },
                Kirigami.Action {
                    visible: spage.md && backend.desktopRunning
                    text: "Hide/show screens"
                    icon.name: "view-visible"
                    onTriggered: backend.toggleScreens()
                },
                Kirigami.Action {
                    visible: backend.desktopRunning
                    text: "Restart desktop"
                    icon.name: "view-refresh"
                    tooltip: "Closes the desktop's windows (and this app) and starts it again"
                    onTriggered: restartDialog.open()
                }
            ]

            header: Kirigami.InlineMessage {
                position: Kirigami.InlineMessage.Position.Header
                visible: backend.restartNeeded || !backend.desktopRunning
                type: Kirigami.MessageType.Information
                text: backend.restartNeeded
                      ? (spage.md ? "Screens were added or removed. That applies when the desktop starts again; restarting closes its windows (and this app)."
                                  : "The number of screens, resolution, or panel width changed. They apply when the desktop starts again; restarting closes its windows (and this app).")
                      : "The desktop isn't running. These settings apply the next time it starts."
                actions: [
                    Kirigami.Action {
                        visible: backend.restartNeeded
                        text: "Restart desktop"
                        icon.name: "system-reboot"
                        onTriggered: backend.restartDesktop()
                    }
                ]
            }

            ColumnLayout {
                spacing: Kirigami.Units.largeSpacing

                // ft-screens: every screen its own resolution and size.
                Repeater {
                    model: spage.md ? backend.screenList : []
                    delegate: Kirigami.AbstractCard {
                        id: card
                        required property var modelData
                        Layout.fillWidth: true
                        property int customIndex: backend.screenResolutions.length
                        contentItem: ColumnLayout {
                            RowLayout {
                                Kirigami.Heading { level: 3; text: "Screen " + (card.modelData.index + 1) }
                                Controls.Label {
                                    text: card.modelData.width + " × " + card.modelData.height
                                          + (card.modelData.scale !== 1 ? ", works like " + card.modelData.effective : "")
                                    opacity: 0.7
                                }
                                Item { Layout.fillWidth: true }
                                Controls.RadioButton {
                                    text: "Taskbar here"
                                    checked: card.modelData.primary
                                    onToggled: if (checked) backend.setPrimary(card.modelData.index)
                                }
                                Controls.ToolButton {
                                    icon.name: "edit-delete-remove"
                                    enabled: backend.screenList.length > 1
                                    display: Controls.AbstractButton.IconOnly
                                    text: "Remove this screen"
                                    Controls.ToolTip.text: text
                                    Controls.ToolTip.visible: hovered
                                    onClicked: backend.removeScreen(card.modelData.index)
                                }
                            }
                            Kirigami.FormLayout {
                                Layout.fillWidth: true
                                RowLayout {
                                    Kirigami.FormData.label: "Resolution:"
                                    Controls.ComboBox {
                                        id: res
                                        model: backend.screenResolutions.concat([{ text: "Custom…", width: 0, height: 0 }])
                                        textRole: "text"
                                        Component.onCompleted: {
                                            const i = backend.screenResolutions.findIndex(r => r.width === card.modelData.width && r.height === card.modelData.height)
                                            currentIndex = i >= 0 ? i : card.customIndex
                                        }
                                        onActivated: {
                                            const r = model[currentIndex]
                                            if (r.width > 0) backend.setScreenSize(card.modelData.index, r.width, r.height)
                                        }
                                    }
                                    Controls.SpinBox {
                                        id: cw
                                        visible: res.currentIndex === card.customIndex
                                        from: 320; to: 16384; stepSize: 8; editable: true
                                        value: card.modelData.width
                                    }
                                    Controls.Label { visible: cw.visible; text: "×" }
                                    Controls.SpinBox {
                                        id: ch
                                        visible: cw.visible
                                        from: 200; to: 16384; stepSize: 8; editable: true
                                        value: card.modelData.height
                                    }
                                    Controls.Button {
                                        visible: cw.visible
                                        text: "Set"
                                        onClicked: backend.setScreenSize(card.modelData.index, cw.value, ch.value)
                                    }
                                }
                                RowLayout {
                                    Kirigami.FormData.label: "Width in VR:"
                                    Controls.Slider {
                                        id: metres
                                        from: 0.5; to: 6.0; stepSize: 0.05
                                        value: card.modelData.metres
                                        Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                                        onMoved: backend.setScreenMetres(card.modelData.index, value)
                                    }
                                    Controls.Label {
                                        text: metres.value.toFixed(2) + " m wide, "
                                              + (metres.value * card.modelData.height / card.modelData.width).toFixed(2) + " m tall"
                                    }
                                }
                                RowLayout {
                                    Kirigami.FormData.label: "Active opacity:"
                                    Controls.Slider {
                                        id: activeOpacitySlider
                                        from: 0.0; to: 1.0; stepSize: 0.05
                                        value: card.modelData.activeOpacity !== undefined
                                               ? card.modelData.activeOpacity
                                               : (card.modelData.opacity !== undefined ? card.modelData.opacity : 1.0)
                                        Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                                        onMoved: backend.setScreenOpacities(card.modelData.index, value, idleOpacitySlider.value)
                                    }
                                    Controls.Label { text: Math.round(activeOpacitySlider.value * 100) + "%" }
                                }
                                RowLayout {
                                    Kirigami.FormData.label: "Idle opacity:"
                                    Controls.Slider {
                                        id: idleOpacitySlider
                                        from: 0.0; to: 1.0; stepSize: 0.05
                                        value: card.modelData.idleOpacity !== undefined
                                               ? card.modelData.idleOpacity
                                               : (card.modelData.opacity !== undefined ? card.modelData.opacity : 1.0)
                                        Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                                        onMoved: backend.setScreenOpacities(card.modelData.index, activeOpacitySlider.value, value)
                                    }
                                    Controls.Label { text: Math.round(idleOpacitySlider.value * 100) + "%" }
                                }
                                Controls.Switch {
                                    id: attentionSwitch
                                    Kirigami.FormData.label: "Gaze attention:"
                                    text: "Fade idle ↔ active from true eye gaze"
                                    checked: card.modelData.attentionEnabled === true
                                    onToggled: backend.setScreenAttention(card.modelData.index, checked)
                                }
                                RowLayout {
                                    visible: attentionSwitch.checked
                                    Kirigami.FormData.label: "Fade in:"
                                    Controls.Slider {
                                        id: fadeInSlider
                                        from: 50; to: 1000; stepSize: 25
                                        value: card.modelData.attentionInMs !== undefined
                                               ? card.modelData.attentionInMs : 150
                                        Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                                        onMoved: backend.setScreenAttentionInMs(card.modelData.index, value)
                                    }
                                    Controls.Label { text: Math.round(fadeInSlider.value) + " ms" }
                                }
                                RowLayout {
                                    visible: attentionSwitch.checked
                                    Kirigami.FormData.label: "Fade out:"
                                    Controls.Slider {
                                        id: fadeOutSlider
                                        from: 50; to: 1000; stepSize: 25
                                        value: card.modelData.attentionOutMs !== undefined
                                               ? card.modelData.attentionOutMs : 250
                                        Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                                        onMoved: backend.setScreenAttentionOutMs(card.modelData.index, value)
                                    }
                                    Controls.Label { text: Math.round(fadeOutSlider.value) + " ms" }
                                }
                                Controls.ComboBox {
                                    Kirigami.FormData.label: "Anchor:"
                                    model: [
                                        { text: "World", value: "world" },
                                        { text: "Head (soft)", value: "head" },
                                        { text: "Yaw follow", value: "yaw-follow" },
                                        { text: "Position follow", value: "position-follow" },
                                        { text: "Left controller", value: "left" },
                                        { text: "Right controller", value: "right" }
                                    ]
                                    textRole: "text"
                                    valueRole: "value"
                                    Component.onCompleted: currentIndex = Math.max(0, indexOfValue(card.modelData.anchor || "world"))
                                    onActivated: backend.setScreenAnchor(card.modelData.index, currentValue)
                                }
                                Controls.Switch {
                                    id: deadzoneSwitch
                                    Kirigami.FormData.label: "Follow dead zone:"
                                    text: "Glance without the panel chasing"
                                    checked: card.modelData.followDeadzone === true
                                    onToggled: backend.setScreenFollowDeadzone(card.modelData.index, checked)
                                }
                                RowLayout {
                                    visible: deadzoneSwitch.checked
                                    Kirigami.FormData.label: "Dead zone:"
                                    Controls.Slider {
                                        id: deadzoneSlider
                                        from: 5; to: 45; stepSize: 1
                                        value: card.modelData.followDeadzoneDeg !== undefined
                                               ? card.modelData.followDeadzoneDeg : 15
                                        Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                                        onMoved: backend.setScreenFollowDeadzoneDeg(card.modelData.index, value)
                                    }
                                    Controls.Label { text: Math.round(deadzoneSlider.value) + "°" }
                                }
                                Controls.ComboBox {
                                    Kirigami.FormData.label: "Scale:"
                                    model: backend.scales
                                    textRole: "text"
                                    valueRole: "value"
                                    Component.onCompleted: currentIndex = Math.max(0, indexOfValue(card.modelData.scale))
                                    onActivated: backend.setScale(card.modelData.index, currentValue)
                                }
                                Controls.Switch {
                                    Kirigami.FormData.label: "Curved:"
                                    text: "Bend around you"
                                    checked: card.modelData.curved
                                    onToggled: backend.setCurved(card.modelData.index, checked)
                                }
                            }
                        }
                    }
                }

                // gamescope: one shared resolution.
                Kirigami.FormLayout {
                    visible: !spage.md
                    Layout.fillWidth: true

                    Controls.SpinBox {
                        Kirigami.FormData.label: "Screens:"
                        from: 1
                        to: 6
                        value: backend.screens
                        onValueModified: backend.setScreens(value)
                    }

                    RowLayout {
                        Kirigami.FormData.label: "Resolution:"
                        Controls.ComboBox {
                            id: resBox
                            property bool custom: currentIndex === count - 1
                            model: backend.resolutions.concat([{ text: "Custom…", width: 0, height: 0 }])
                            textRole: "text"
                            Component.onCompleted: {
                                const i = backend.resolutions.findIndex(r => r.width === backend.width && r.height === backend.height)
                                currentIndex = i >= 0 ? i : count - 1
                            }
                            onActivated: {
                                const r = model[currentIndex]
                                if (r.width > 0) backend.setResolution(r.width, r.height)
                            }
                        }
                        Controls.SpinBox {
                            id: customW
                            visible: resBox.custom
                            from: 640; to: 7680; stepSize: 8
                            editable: true
                            value: backend.width
                        }
                        Controls.Label { visible: resBox.custom; text: "×" }
                        Controls.SpinBox {
                            id: customH
                            visible: resBox.custom
                            from: 360; to: 4320; stepSize: 8
                            editable: true
                            value: backend.height
                        }
                        Controls.Button {
                            visible: resBox.custom
                            text: "Set"
                            onClicked: backend.setResolution(customW.value, customH.value)
                        }
                    }

                    RowLayout {
                        Kirigami.FormData.label: "Panel width:"
                        Controls.Slider {
                            id: physSlider
                            from: 0.8; to: 3.0; stepSize: 0.05
                            value: backend.physWidth
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                            onMoved: backend.setPhysWidth(value)
                        }
                        Controls.Label { text: physSlider.value.toFixed(2) + " m" }
                    }

                    Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: "Each screen" }

                    Repeater {
                        model: spage.md ? [] : backend.screenList
                        delegate: RowLayout {
                            required property var modelData
                            Kirigami.FormData.label: "Screen " + (modelData.index + 1) + ":"
                            Controls.ComboBox {
                                model: backend.rotations
                                textRole: "text"
                                valueRole: "value"
                                Component.onCompleted: currentIndex = Math.max(0, indexOfValue(modelData.rotation))
                                onActivated: backend.setRotation(modelData.index, currentValue)
                            }
                            Controls.ComboBox {
                                model: backend.scales
                                textRole: "text"
                                valueRole: "value"
                                Component.onCompleted: currentIndex = Math.max(0, indexOfValue(modelData.scale))
                                onActivated: backend.setScale(modelData.index, currentValue)
                            }
                            Controls.Label {
                                text: "looks like " + modelData.effective
                                opacity: 0.7
                            }
                        }
                    }
                }
            }

            footer: Controls.Label {
                padding: Kirigami.Units.largeSpacing
                wrapMode: Text.Wrap
                opacity: 0.7
                text: spage.md
                      ? "Each screen is a real monitor of its own: any resolution, portrait by choosing a tall one. Resolution, "
                        + "width, and curve apply at once. In VR: move a screen by the bar underneath, curve it with the round "
                        + "button next to the bar, resize it by the tab on its bottom right corner; Save current arrangement on the "
                        + "Layout page keeps all of it."
                      : "gamescope draws every screen at the same resolution, at most 1920 × 1080 worth of pixels. Portrait turns "
                        + "a screen on its side. Rotation and scale apply at once; the rest when the desktop starts."
            }
        }
    }

    // ---------------------------------------------------------------- Spatial Instruments
    Component {
        id: instrumentsPage
        Kirigami.ScrollablePage {
            id: ipage
            title: "Spatial Instruments"
            property var clock: backend.clockInstrument
            property var date: backend.dateInstrument
            property var battery: backend.batteryInstrument
            property var storage: backend.storageInstrument
            property var sd: backend.sdInstrument
            property var media: backend.mediaInstrument
            property var images: backend.imageInstruments
            property var launchers: backend.launcherInstruments
            property var apps: backend.installedApps
            property var actions: backend.semanticActions
            property var glyphs: backend.launcherGlyphs
            property var colorPresets: backend.instrumentColorPresets
            property string pendingImageId: "image"
            property string pendingLauncherFileId: "launcher"

            // Which card's settings sheet is open: "clock"|"date"|… or "image:<id>"|"launcher:<id>"
            property string editKey: ""
            property var editImage: null
            property var editLauncher: null

            readonly property var anchorChoices: [
                { text: "World", value: "world" },
                { text: "Position-follow", value: "position-follow" },
                { text: "Yaw-follow", value: "yaw-follow" },
                { text: "Head (soft)", value: "head" },
                { text: "Head (rigid)", value: "head-rigid" }
            ]

            function openBuiltin(key) { editImage = null; editLauncher = null; editKey = key }
            function openImage(img) { editLauncher = null; editImage = img; editKey = "image:" + img.id }
            function openLauncher(ln) { editImage = null; editLauncher = ln; editKey = "launcher:" + ln.id }
            function closeEdit() { editKey = ""; editImage = null; editLauncher = null }

            // Quiet plate behind instrument previews (VR textures are transparent overlays).
            component PreviewPlate: Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Kirigami.Units.gridUnit * 4.5
                color: Qt.rgba(0.07, 0.08, 0.10, 1)
                radius: 3
                property bool lit: true
                opacity: lit ? 1 : 0.35
            }

            ColumnLayout {
                spacing: Kirigami.Units.largeSpacing

                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.75
                    text: "Ambient overlays in VR space — not desktop windows. Previews match what ft-screens "
                          + "actually draws. Gaze brightens; laser-click a Launcher to open it."
                }

                RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Controls.Button {
                        text: "Add Image"
                        icon.name: "insert-image"
                        enabled: backend.busy === ""
                        onClicked: backend.addImageInstrument()
                    }
                    Controls.Button {
                        text: "Add Launcher"
                        icon.name: "application-x-executable"
                        enabled: backend.busy === ""
                        onClicked: backend.addLauncherInstrument()
                    }
                    Item { Layout.fillWidth: true }
                }

                Controls.Label {
                    text: "Built-in"
                    font.bold: true
                    Layout.topMargin: Kirigami.Units.smallSpacing
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: Kirigami.Units.largeSpacing
                    rowSpacing: Kirigami.Units.largeSpacing

                    // Honest previews: same geometry language as screens/vr.cpp instrument textures
                    // (7-seg digits, 5×7 glyphs, segment battery, usage bar + icon, media transport).

                    // ---- Clock (7-segment HH:MM)
                    Kirigami.AbstractCard {
                        Layout.fillWidth: true
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 18
                        contentItem: ColumnLayout {
                            spacing: Kirigami.Units.smallSpacing
                            PreviewPlate {
                                lit: clock.enabled === true
                                Canvas {
                                    id: clockCanvas
                                    anchors.fill: parent
                                    anchors.margins: 8
                                    property color ink: clock.color || "#39FF14"
                                    onInkChanged: requestPaint()
                                    onWidthChanged: requestPaint()
                                    onHeightChanged: requestPaint()
                                    // Digits 1 4 : 3 5 — mirrors DrawSegDigit / RefreshClockTexture
                                    readonly property var masks: [0x77, 0x24, 0x5d, 0x6d, 0x2e, 0x6b, 0x7b, 0x25, 0x7f, 0x6f]
                                    function drawDigit(ctx, ox, oy, dw, dh, digit, color) {
                                        const bits = masks[digit]
                                        const t = Math.max(2, Math.floor(dw / 8))
                                        const mid = oy + dh / 2
                                        ctx.fillStyle = color
                                        function segH(y) { ctx.fillRect(ox + t, y - t / 2, dw - 2 * t, t) }
                                        function segV(x, y0, y1) { ctx.fillRect(x - t / 2, y0 + t / 2, t, Math.max(1, y1 - y0 - t)) }
                                        if (bits & 0x01) segH(oy + t)
                                        if (bits & 0x02) segV(ox + t, oy, mid)
                                        if (bits & 0x04) segV(ox + dw - t, oy, mid)
                                        if (bits & 0x08) segH(mid)
                                        if (bits & 0x10) segV(ox + t, mid, oy + dh)
                                        if (bits & 0x20) segV(ox + dw - t, mid, oy + dh)
                                        if (bits & 0x40) segH(oy + dh - t)
                                    }
                                    onPaint: {
                                        const ctx = getContext("2d")
                                        ctx.reset()
                                        const w = width, h = height
                                        const dw = Math.min(28, w / 7), dh = Math.min(44, h * 0.75)
                                        const gap = 7, colon = 10
                                        const total = 4 * dw + 3 * gap + colon
                                        let ox = (w - total) / 2
                                        const oy = (h - dh) / 2
                                        const digits = [1, 4, 3, 5]
                                        for (let i = 0; i < 4; ++i) {
                                            if (i === 2) {
                                                const cx = ox + 2
                                                ctx.fillStyle = ink
                                                ctx.fillRect(cx, oy + dh / 3 - 3, 5, 6)
                                                ctx.fillRect(cx, oy + 2 * dh / 3 - 3, 5, 6)
                                                ox += colon
                                            }
                                            drawDigit(ctx, ox, oy, dw, dh, digits[i], ink)
                                            ox += dw + gap
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                Controls.Label { text: "Clock"; font.bold: true; Layout.fillWidth: true }
                                Controls.Switch {
                                    checked: clock.enabled === true
                                    onToggled: backend.setClockEnabled(checked)
                                }
                            }
                            Controls.Label {
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                opacity: 0.7
                                text: "Seven-segment HH:MM floating in space (transparent backdrop)."
                                font: Kirigami.Theme.smallFont
                            }
                            Controls.Button {
                                text: "Configure…"
                                flat: true
                                onClicked: ipage.openBuiltin("clock")
                            }
                        }
                    }

                    // ---- Date (5×7 weekday/month + 7-seg day-of-month)
                    Kirigami.AbstractCard {
                        Layout.fillWidth: true
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 18
                        contentItem: ColumnLayout {
                            spacing: Kirigami.Units.smallSpacing
                            PreviewPlate {
                                lit: date.enabled === true
                                Canvas {
                                    id: dateCanvas
                                    anchors.fill: parent
                                    anchors.margins: 8
                                    property color ink: date.color || "#39FF14"
                                    onInkChanged: requestPaint()
                                    onWidthChanged: requestPaint()
                                    onHeightChanged: requestPaint()
                                    readonly property var masks: [0x77, 0x24, 0x5d, 0x6d, 0x2e, 0x6b, 0x7b, 0x25, 0x7f, 0x6f]
                                    // 5×7 rows for letters used in WED / SEP (bit4 = left)
                                    readonly property var glyphs: ({
                                        "W": [0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11],
                                        "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
                                        "D": [0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E],
                                        "S": [0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E],
                                        "P": [0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10]
                                    })
                                    function drawDigit(ctx, ox, oy, dw, dh, digit, color) {
                                        const bits = masks[digit]
                                        const t = Math.max(2, Math.floor(dw / 8))
                                        const mid = oy + dh / 2
                                        ctx.fillStyle = color
                                        function segH(y) { ctx.fillRect(ox + t, y - t / 2, dw - 2 * t, t) }
                                        function segV(x, y0, y1) { ctx.fillRect(x - t / 2, y0 + t / 2, t, Math.max(1, y1 - y0 - t)) }
                                        if (bits & 0x01) segH(oy + t)
                                        if (bits & 0x02) segV(ox + t, oy, mid)
                                        if (bits & 0x04) segV(ox + dw - t, oy, mid)
                                        if (bits & 0x08) segH(mid)
                                        if (bits & 0x10) segV(ox + t, mid, oy + dh)
                                        if (bits & 0x20) segV(ox + dw - t, mid, oy + dh)
                                        if (bits & 0x40) segH(oy + dh - t)
                                    }
                                    function drawWord(ctx, ox, oy, cell, word, color) {
                                        const scale = Math.max(2, Math.floor(cell / 7))
                                        const adv = 5 * scale + scale
                                        ctx.fillStyle = color
                                        for (let i = 0; i < word.length; ++i) {
                                            const rows = glyphs[word[i]] || [0,0,0,0,0,0,0]
                                            for (let row = 0; row < 7; ++row) {
                                                const bits = rows[row]
                                                for (let col = 0; col < 5; ++col) {
                                                    if (!(bits & (1 << (4 - col)))) continue
                                                    ctx.fillRect(ox + i * adv + col * scale, oy + row * scale, scale - 0.5, scale - 0.5)
                                                }
                                            }
                                        }
                                        return word.length * adv - scale
                                    }
                                    onPaint: {
                                        const ctx = getContext("2d")
                                        ctx.reset()
                                        const w = width, h = height
                                        const cell = 12, dw = 18, dh = 30, dgap = 4, gap = 10
                                        const dayW = 3 * (5 * Math.max(2, Math.floor(cell / 7)) + Math.max(2, Math.floor(cell / 7))) - Math.max(2, Math.floor(cell / 7))
                                        const monW = dayW
                                        const numW = 2 * dw + dgap
                                        const total = dayW + gap + numW + gap + monW
                                        let ox = (w - total) / 2
                                        const letterOy = (h - 7 * Math.max(2, Math.floor(cell / 7))) / 2
                                        const digitOy = (h - dh) / 2
                                        const dim = Qt.rgba(ink.r * 0.85, ink.g * 0.88, ink.b * 0.9, 1)
                                        ox += drawWord(ctx, ox, letterOy, cell, "WED", dim) + gap
                                        drawDigit(ctx, ox, digitOy, dw, dh, 3, ink)
                                        ox += dw + dgap
                                        drawDigit(ctx, ox, digitOy, dw, dh, 0, ink)
                                        ox += dw + gap
                                        drawWord(ctx, ox, letterOy, cell, "SEP", dim)
                                    }
                                }
                            }
                            RowLayout {
                                Controls.Label { text: "Date"; font.bold: true; Layout.fillWidth: true }
                                Controls.Switch {
                                    checked: date.enabled === true
                                    onToggled: backend.setDateEnabled(checked)
                                }
                            }
                            Controls.Label {
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                opacity: 0.7
                                text: "Pixel weekday + seven-segment day + pixel month (WED 30 SEP)."
                                font: Kirigami.Theme.smallFont
                            }
                            Controls.Button {
                                text: "Configure…"
                                flat: true
                                onClicked: ipage.openBuiltin("date")
                            }
                        }
                    }

                    // ---- Battery (five rounded blocks only — no percent text)
                    Kirigami.AbstractCard {
                        Layout.fillWidth: true
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 18
                        contentItem: ColumnLayout {
                            spacing: Kirigami.Units.smallSpacing
                            PreviewPlate {
                                lit: battery.enabled === true
                                Row {
                                    anchors.centerIn: parent
                                    spacing: 6
                                    Repeater {
                                        model: 5
                                        Rectangle {
                                            required property int index
                                            width: 22
                                            height: 18
                                            radius: 3
                                            color: battery.color || "#39FF14"
                                            opacity: index < 4 ? 0.92 : 0.28
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                Controls.Label { text: "Battery"; font.bold: true; Layout.fillWidth: true }
                                Controls.Switch {
                                    checked: battery.enabled === true
                                    onToggled: backend.setBatteryEnabled(checked)
                                }
                            }
                            Controls.Label {
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                opacity: 0.7
                                text: "Five rounded charge blocks for the headset — no digits."
                                font: Kirigami.Theme.smallFont
                            }
                            Controls.Button {
                                text: "Configure…"
                                flat: true
                                onClicked: ipage.openBuiltin("battery")
                            }
                        }
                    }

                    // ---- Media (glyph title + geometric prev / play|pause / next)
                    Kirigami.AbstractCard {
                        Layout.fillWidth: true
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 18
                        contentItem: ColumnLayout {
                            spacing: Kirigami.Units.smallSpacing
                            PreviewPlate {
                                lit: media.enabled === true
                                Canvas {
                                    anchors.fill: parent
                                    anchors.margins: 6
                                    property color ink: media.color || "#39FF14"
                                    onInkChanged: requestPaint()
                                    onWidthChanged: requestPaint()
                                    onHeightChanged: requestPaint()
                                    onPaint: {
                                        const ctx = getContext("2d")
                                        ctx.reset()
                                        const w = width, h = height
                                        // Sample track line (pixel-ish dashes), then transport icons
                                        ctx.fillStyle = ink
                                        const label = "TRACK — ARTIST"
                                        ctx.font = "bold 11px monospace"
                                        ctx.fillText(label, (w - ctx.measureText(label).width) / 2, 18)
                                        const by = h - 22
                                        const third = w / 3
                                        function prev(cx) {
                                            ctx.fillRect(cx - 10, by - 6, 3, 12)
                                            ctx.beginPath()
                                            ctx.moveTo(cx + 6, by - 7); ctx.lineTo(cx - 4, by); ctx.lineTo(cx + 6, by + 7); ctx.closePath(); ctx.fill()
                                        }
                                        function pause(cx) {
                                            ctx.fillRect(cx - 6, by - 7, 4, 14)
                                            ctx.fillRect(cx + 2, by - 7, 4, 14)
                                        }
                                        function next(cx) {
                                            ctx.beginPath()
                                            ctx.moveTo(cx - 6, by - 7); ctx.lineTo(cx + 4, by); ctx.lineTo(cx - 6, by + 7); ctx.closePath(); ctx.fill()
                                            ctx.fillRect(cx + 5, by - 6, 3, 12)
                                        }
                                        prev(third / 2)
                                        pause(third + third / 2)
                                        next(2 * third + third / 2)
                                    }
                                }
                            }
                            RowLayout {
                                Controls.Label { text: "Media"; font.bold: true; Layout.fillWidth: true }
                                Controls.Switch {
                                    checked: media.enabled === true
                                    onToggled: backend.setMediaEnabled(checked)
                                }
                            }
                            Controls.Label {
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                opacity: 0.7
                                text: "Scrolling track text with prev / pause / next glyphs underneath."
                                font: Kirigami.Theme.smallFont
                            }
                            Controls.Button {
                                text: "Configure…"
                                flat: true
                                onClicked: ipage.openBuiltin("media")
                            }
                        }
                    }

                    // ---- Device storage (disk icon + usage bar)
                    Kirigami.AbstractCard {
                        Layout.fillWidth: true
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 18
                        contentItem: ColumnLayout {
                            spacing: Kirigami.Units.smallSpacing
                            PreviewPlate {
                                lit: storage.enabled === true
                                Item {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    // Disk glyph
                                    Rectangle {
                                        id: diskGlyph
                                        width: 18; height: 18
                                        anchors.verticalCenter: parent.verticalCenter
                                        x: 4
                                        color: "#78d2e6"
                                        Rectangle {
                                            anchors.centerIn: parent
                                            width: 8; height: 8
                                            color: Qt.rgba(0.08, 0.09, 0.11, 0.85)
                                        }
                                    }
                                    // Usage track + fill (~55%)
                                    Rectangle {
                                        anchors.verticalCenter: parent.verticalCenter
                                        anchors.left: diskGlyph.right
                                        anchors.leftMargin: 10
                                        anchors.right: parent.right
                                        height: 16
                                        radius: 3
                                        color: Qt.rgba(0.27, 0.30, 0.37, 0.45)
                                        Rectangle {
                                            width: parent.width * 0.55
                                            height: parent.height - 4
                                            anchors.verticalCenter: parent.verticalCenter
                                            x: 2
                                            radius: 2
                                            color: "#78d2e6"
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                Controls.Label { text: "Device storage"; font.bold: true; Layout.fillWidth: true }
                                Controls.Switch {
                                    checked: storage.enabled === true
                                    onToggled: backend.setStorageEnabled(checked)
                                }
                            }
                            Controls.Label {
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                opacity: 0.7
                                text: "Small disk icon and a fill bar for used space — no free-GB caption."
                                font: Kirigami.Theme.smallFont
                            }
                            Controls.Button {
                                text: "Configure…"
                                flat: true
                                onClicked: ipage.openBuiltin("storage")
                            }
                        }
                    }

                    // ---- SD card (notched card + usage bar)
                    Kirigami.AbstractCard {
                        Layout.fillWidth: true
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 18
                        contentItem: ColumnLayout {
                            spacing: Kirigami.Units.smallSpacing
                            PreviewPlate {
                                lit: sd.enabled === true
                                Item {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    Item {
                                        id: sdGlyph
                                        width: 18; height: 20
                                        anchors.verticalCenter: parent.verticalCenter
                                        x: 4
                                        Rectangle {
                                            x: 2; width: 14; height: 20
                                            color: "#78d2e6"
                                        }
                                        Rectangle {
                                            x: 0; y: 4; width: 4; height: 6
                                            color: "#78d2e6"
                                        }
                                        Rectangle {
                                            x: 6; y: 4; width: 6; height: 4
                                            color: Qt.rgba(0.08, 0.09, 0.11, 0.85)
                                        }
                                    }
                                    Rectangle {
                                        anchors.verticalCenter: parent.verticalCenter
                                        anchors.left: sdGlyph.right
                                        anchors.leftMargin: 10
                                        anchors.right: parent.right
                                        height: 16
                                        radius: 3
                                        color: Qt.rgba(0.27, 0.30, 0.37, 0.45)
                                        Rectangle {
                                            width: parent.width * 0.35
                                            height: parent.height - 4
                                            anchors.verticalCenter: parent.verticalCenter
                                            x: 2
                                            radius: 2
                                            color: "#78d2e6"
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                Controls.Label { text: "SD card"; font.bold: true; Layout.fillWidth: true }
                                Controls.Switch {
                                    checked: sd.enabled === true
                                    onToggled: backend.setSdEnabled(checked)
                                }
                            }
                            Controls.Label {
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                opacity: 0.7
                                text: "Notched SD glyph and a fill bar (empty bar if no card)."
                                font: Kirigami.Theme.smallFont
                            }
                            Controls.Button {
                                text: "Configure…"
                                flat: true
                                onClicked: ipage.openBuiltin("sd")
                            }
                        }
                    }
                }

                Controls.Label {
                    visible: images.length > 0
                    text: "Images"
                    font.bold: true
                    Layout.topMargin: Kirigami.Units.smallSpacing
                }

                GridLayout {
                    visible: images.length > 0
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: Kirigami.Units.largeSpacing
                    rowSpacing: Kirigami.Units.largeSpacing

                    Repeater {
                        model: images
                        delegate: Kirigami.AbstractCard {
                            Layout.fillWidth: true
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 18
                            readonly property var img: modelData
                            contentItem: ColumnLayout {
                                spacing: Kirigami.Units.smallSpacing
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Kirigami.Units.gridUnit * 4.5
                                    color: Qt.rgba(0.07, 0.08, 0.10, 1)
                                    radius: 3
                                    opacity: (img && img.enabled) ? 1 : 0.35
                                    // Checkerboard = transparent PNG/GIF floating in VR
                                    Canvas {
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        onWidthChanged: requestPaint()
                                        onHeightChanged: requestPaint()
                                        onPaint: {
                                            const ctx = getContext("2d")
                                            ctx.reset()
                                            const s = 8
                                            for (let y = 0; y < height; y += s)
                                                for (let x = 0; x < width; x += s) {
                                                    ctx.fillStyle = ((x / s + y / s) % 2 === 0)
                                                        ? Qt.rgba(0.18, 0.19, 0.22, 1)
                                                        : Qt.rgba(0.12, 0.13, 0.15, 1)
                                                    ctx.fillRect(x, y, s, s)
                                                }
                                            ctx.strokeStyle = Qt.rgba(0.55, 0.58, 0.62, 0.9)
                                            ctx.lineWidth = 2
                                            ctx.strokeRect(width * 0.2, height * 0.15, width * 0.6, height * 0.7)
                                        }
                                    }
                                    Controls.Label {
                                        anchors.centerIn: parent
                                        text: (img && img.fileName) ? img.fileName : "no file yet"
                                        elide: Text.ElideMiddle
                                        width: parent.width - 24
                                        horizontalAlignment: Text.AlignHCenter
                                        font: Kirigami.Theme.smallFont
                                        color: Kirigami.Theme.textColor
                                    }
                                }
                                RowLayout {
                                    Controls.Label {
                                        text: (img && img.label) ? img.label : "Image"
                                        font.bold: true
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }
                                    Controls.Switch {
                                        checked: !!(img && img.enabled)
                                        onToggled: backend.setImageEnabled(img.id, checked)
                                    }
                                }
                                Controls.Label {
                                    Layout.fillWidth: true
                                    wrapMode: Text.Wrap
                                    opacity: 0.7
                                    text: "Your image floats as raw pixels with alpha — no window chrome."
                                    font: Kirigami.Theme.smallFont
                                }
                                Controls.Button {
                                    text: "Configure…"
                                    flat: true
                                    onClicked: ipage.openImage(img)
                                }
                            }
                        }
                    }
                }

                Controls.Label {
                    visible: launchers.length > 0
                    text: "Launchers"
                    font.bold: true
                    Layout.topMargin: Kirigami.Units.smallSpacing
                }

                GridLayout {
                    visible: launchers.length > 0
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: Kirigami.Units.largeSpacing
                    rowSpacing: Kirigami.Units.largeSpacing

                    Repeater {
                        model: launchers
                        delegate: Kirigami.AbstractCard {
                            Layout.fillWidth: true
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 18
                            readonly property var ln: modelData
                            contentItem: ColumnLayout {
                                spacing: Kirigami.Units.smallSpacing
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Kirigami.Units.gridUnit * 4.5
                                    color: Qt.rgba(0.07, 0.08, 0.10, 1)
                                    radius: 3
                                    opacity: (ln && ln.enabled) ? 1 : 0.35
                                    // Square icon face like the VR launcher overlay (not a window)
                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: Math.min(parent.height - 16, 56)
                                        height: width
                                        radius: 10
                                        color: Qt.rgba(0.16, 0.18, 0.22, 1)
                                        border.color: Qt.rgba(0.45, 0.48, 0.55, 0.8)
                                        border.width: 1
                                        Controls.Label {
                                            anchors.centerIn: parent
                                            text: (ln && ln.title) ? ln.title.charAt(0) : "?"
                                            font.pixelSize: parent.width * 0.4
                                            font.bold: true
                                        }
                                    }
                                }
                                RowLayout {
                                    Controls.Label {
                                        text: (ln && ln.title) ? ln.title : "Launcher"
                                        font.bold: true
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }
                                    Controls.Switch {
                                        checked: !!(ln && ln.enabled)
                                        onToggled: backend.setLauncherEnabled(ln.id, checked)
                                    }
                                }
                                Controls.Label {
                                    Layout.fillWidth: true
                                    wrapMode: Text.Wrap
                                    opacity: 0.7
                                    text: "Square icon face in VR (app icon / glyph). Laser-click opens; bar moves."
                                    font: Kirigami.Theme.smallFont
                                    color: (ln && ln.actionKind === "application" && ln.desktopId && ln.appAvailable === false)
                                           ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                                }
                                Controls.Button {
                                    text: "Configure…"
                                    flat: true
                                    onClicked: ipage.openLauncher(ln)
                                }
                            }
                        }
                    }
                }

                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.65
                    text: "In VR: laser on an instrument shows its move bar; drag to place, scroll to push/pull. "
                          + "Launcher icon click activates; bar drag moves. Profiles replace the whole set."
                }
            }

            // -------- settings dialog (one shared)
            Kirigami.Dialog {
                id: editSheet
                title: editKey.indexOf("launcher:") === 0 ? ((editLauncher && editLauncher.title) || "Launcher")
                     : editKey.indexOf("image:") === 0 ? ((editImage && editImage.label) || "Image")
                     : editKey === "clock" ? "Clock"
                     : editKey === "date" ? "Date"
                     : editKey === "battery" ? "Battery"
                     : editKey === "media" ? "Media"
                     : editKey === "storage" ? "Device storage"
                     : editKey === "sd" ? "SD card"
                     : "Instrument"
                standardButtons: Kirigami.Dialog.Close
                preferredWidth: Math.min(Kirigami.Units.gridUnit * 30, ipage.width * 0.92)
                onClosed: ipage.closeEdit()

                // Open/close when editKey changes
                Connections {
                    target: ipage
                    function onEditKeyChanged() {
                        if (ipage.editKey !== "")
                            editSheet.open()
                        else if (editSheet.opened)
                            editSheet.close()
                    }
                }

                ColumnLayout {
                    spacing: Kirigami.Units.largeSpacing
                    width: Math.min(Kirigami.Units.gridUnit * 28, ipage.width * 0.9)

                    // Shared controls for built-ins (clock/date/battery/media/storage/sd)
                    Kirigami.FormLayout {
                        Layout.fillWidth: true
                        visible: ["clock", "date", "battery", "media", "storage", "sd"].indexOf(editKey) >= 0

                        Controls.ComboBox {
                            id: builtinAnchor
                            Kirigami.FormData.label: "Anchor:"
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 14
                            model: ipage.anchorChoices
                            textRole: "text"
                            valueRole: "value"
                            function syncFrom() {
                                const d = editKey === "clock" ? clock
                                        : editKey === "date" ? date
                                        : editKey === "battery" ? battery
                                        : editKey === "media" ? media
                                        : editKey === "storage" ? storage
                                        : sd
                                currentIndex = Math.max(0, indexOfValue((d && d.anchor) || "world"))
                            }
                            Component.onCompleted: syncFrom()
                            Connections { target: ipage; function onEditKeyChanged() { builtinAnchor.syncFrom() } }
                            onActivated: {
                                if (editKey === "clock") backend.setClockAnchor(currentValue)
                                else if (editKey === "date") backend.setDateAnchor(currentValue)
                                else if (editKey === "battery") backend.setBatteryAnchor(currentValue)
                                else if (editKey === "media") backend.setMediaAnchor(currentValue)
                                else if (editKey === "storage") backend.setStorageAnchor(currentValue)
                                else if (editKey === "sd") backend.setSdAnchor(currentValue)
                            }
                        }
                        Controls.SpinBox {
                            id: builtinMetres
                            Kirigami.FormData.label: "Size (metres):"
                            from: 8; to: 200; stepSize: 5
                            function syncFrom() {
                                const d = editKey === "clock" ? clock
                                        : editKey === "date" ? date
                                        : editKey === "battery" ? battery
                                        : editKey === "media" ? media
                                        : editKey === "storage" ? storage
                                        : sd
                                const def = editKey === "clock" ? 0.35
                                          : editKey === "date" ? 0.38
                                          : editKey === "battery" ? 0.32
                                          : editKey === "media" ? 0.42
                                          : 0.34
                                value = Math.round(((d && d.metres !== undefined) ? d.metres : def) * 100)
                            }
                            Component.onCompleted: syncFrom()
                            Connections { target: ipage; function onEditKeyChanged() { builtinMetres.syncFrom() } }
                            textFromValue: (v) => (v / 100).toFixed(2)
                            valueFromText: (t) => Math.round(parseFloat(t) * 100)
                            onValueModified: {
                                const m = value / 100
                                if (editKey === "clock") backend.setClockMetres(m)
                                else if (editKey === "date") backend.setDateMetres(m)
                                else if (editKey === "battery") backend.setBatteryMetres(m)
                                else if (editKey === "media") backend.setMediaMetres(m)
                                else if (editKey === "storage") backend.setStorageMetres(m)
                                else if (editKey === "sd") backend.setSdMetres(m)
                            }
                        }
                        Controls.SpinBox {
                            id: builtinIdle
                            Kirigami.FormData.label: "Idle opacity:"
                            from: 0; to: 100; stepSize: 5
                            function syncFrom() {
                                const d = editKey === "clock" ? clock
                                        : editKey === "date" ? date
                                        : editKey === "battery" ? battery
                                        : editKey === "media" ? media
                                        : editKey === "storage" ? storage
                                        : sd
                                value = Math.round(((d && d.idleOpacity !== undefined) ? d.idleOpacity : 0.35) * 100)
                            }
                            Component.onCompleted: syncFrom()
                            Connections { target: ipage; function onEditKeyChanged() { builtinIdle.syncFrom() } }
                            textFromValue: (v) => (v / 100).toFixed(2)
                            valueFromText: (t) => Math.round(parseFloat(t) * 100)
                            onValueModified: {
                                const v = value / 100
                                if (editKey === "clock") backend.setClockIdleOpacity(v)
                                else if (editKey === "date") backend.setDateIdleOpacity(v)
                                else if (editKey === "battery") backend.setBatteryIdleOpacity(v)
                                else if (editKey === "media") backend.setMediaIdleOpacity(v)
                                else if (editKey === "storage") backend.setStorageIdleOpacity(v)
                                else if (editKey === "sd") backend.setSdIdleOpacity(v)
                            }
                        }
                        Controls.SpinBox {
                            id: builtinActive
                            Kirigami.FormData.label: "Active opacity:"
                            from: 0; to: 100; stepSize: 5
                            function syncFrom() {
                                const d = editKey === "clock" ? clock
                                        : editKey === "date" ? date
                                        : editKey === "battery" ? battery
                                        : editKey === "media" ? media
                                        : editKey === "storage" ? storage
                                        : sd
                                value = Math.round(((d && d.activeOpacity !== undefined) ? d.activeOpacity : 1.0) * 100)
                            }
                            Component.onCompleted: syncFrom()
                            Connections { target: ipage; function onEditKeyChanged() { builtinActive.syncFrom() } }
                            textFromValue: (v) => (v / 100).toFixed(2)
                            valueFromText: (t) => Math.round(parseFloat(t) * 100)
                            onValueModified: {
                                const v = value / 100
                                if (editKey === "clock") backend.setClockActiveOpacity(v)
                                else if (editKey === "date") backend.setDateActiveOpacity(v)
                                else if (editKey === "battery") backend.setBatteryActiveOpacity(v)
                                else if (editKey === "media") backend.setMediaActiveOpacity(v)
                                else if (editKey === "storage") backend.setStorageActiveOpacity(v)
                                else if (editKey === "sd") backend.setSdActiveOpacity(v)
                            }
                        }
                        Controls.Switch {
                            id: builtinAttn
                            Kirigami.FormData.label: "Gaze attention:"
                            function syncFrom() {
                                const d = editKey === "clock" ? clock
                                        : editKey === "date" ? date
                                        : editKey === "battery" ? battery
                                        : editKey === "media" ? media
                                        : editKey === "storage" ? storage
                                        : sd
                                checked = !(d && d.attentionEnabled === false)
                            }
                            Component.onCompleted: syncFrom()
                            Connections { target: ipage; function onEditKeyChanged() { builtinAttn.syncFrom() } }
                            onToggled: {
                                if (editKey === "clock") backend.setClockAttention(checked)
                                else if (editKey === "date") backend.setDateAttention(checked)
                                else if (editKey === "battery") backend.setBatteryAttention(checked)
                                else if (editKey === "media") backend.setMediaAttention(checked)
                                else if (editKey === "storage") backend.setStorageAttention(checked)
                                else if (editKey === "sd") backend.setSdAttention(checked)
                            }
                        }
                        Controls.ComboBox {
                            id: builtinColor
                            visible: ["clock", "date", "battery", "media"].indexOf(editKey) >= 0
                            Kirigami.FormData.label: "Colour:"
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 14
                            model: colorPresets
                            textRole: "text"
                            valueRole: "value"
                            function syncFrom() {
                                const d = editKey === "clock" ? clock
                                        : editKey === "date" ? date
                                        : editKey === "battery" ? battery
                                        : media
                                currentIndex = Math.max(0, indexOfValue((d && d.color) || "#39FF14"))
                            }
                            Component.onCompleted: syncFrom()
                            Connections { target: ipage; function onEditKeyChanged() { builtinColor.syncFrom() } }
                            onActivated: {
                                if (editKey === "clock") backend.setClockColor(currentValue)
                                else if (editKey === "date") backend.setDateColor(currentValue)
                                else if (editKey === "battery") backend.setBatteryColor(currentValue)
                                else if (editKey === "media") backend.setMediaColor(currentValue)
                            }
                        }
                        Controls.Button {
                            Kirigami.FormData.label: " "
                            text: "Place in front of me"
                            enabled: backend.desktopRunning && backend.busy === ""
                            onClicked: {
                                if (editKey === "clock") backend.recenterClock()
                                else if (editKey === "date") backend.recenterDate()
                                else if (editKey === "battery") backend.recenterBattery()
                                else if (editKey === "media") backend.recenterMedia()
                                else if (editKey === "storage") backend.recenterStorage()
                                else if (editKey === "sd") backend.recenterSd()
                            }
                        }
                    }

                    // Image settings
                    Kirigami.FormLayout {
                        Layout.fillWidth: true
                        visible: editKey.indexOf("image:") === 0 && editImage
                        readonly property var img: editImage

                        Controls.ComboBox {
                            Kirigami.FormData.label: "Anchor:"
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 14
                            model: ipage.anchorChoices
                            textRole: "text"
                            valueRole: "value"
                            Component.onCompleted: currentIndex = Math.max(0, indexOfValue((img && img.anchor) || "world"))
                            onActivated: if (img) backend.setImageAnchor(img.id, currentValue)
                        }
                        Controls.Label {
                            Kirigami.FormData.label: "File:"
                            Layout.fillWidth: true
                            elide: Text.ElideMiddle
                            text: (img && img.fileName) ? img.fileName : "(none — pick a PNG or GIF)"
                            opacity: (img && img.fileName) ? 1.0 : 0.6
                        }
                        Controls.Button {
                            Kirigami.FormData.label: " "
                            text: "Choose image…"
                            enabled: backend.busy === ""
                            onClicked: {
                                pendingImageId = img.id
                                imageFileDialog.open()
                            }
                        }
                        Controls.SpinBox {
                            Kirigami.FormData.label: "Size (metres):"
                            from: 8; to: 200; stepSize: 5
                            value: Math.round(((img && img.metres !== undefined) ? img.metres : 0.50) * 100)
                            textFromValue: (v) => (v / 100).toFixed(2)
                            valueFromText: (t) => Math.round(parseFloat(t) * 100)
                            onValueModified: if (img) backend.setImageMetres(img.id, value / 100)
                        }
                        Controls.SpinBox {
                            Kirigami.FormData.label: "Idle opacity:"
                            from: 0; to: 100; stepSize: 5
                            value: Math.round(((img && img.idleOpacity !== undefined) ? img.idleOpacity : 0.35) * 100)
                            textFromValue: (v) => (v / 100).toFixed(2)
                            valueFromText: (t) => Math.round(parseFloat(t) * 100)
                            onValueModified: if (img) backend.setImageIdleOpacity(img.id, value / 100)
                        }
                        Controls.SpinBox {
                            Kirigami.FormData.label: "Active opacity:"
                            from: 0; to: 100; stepSize: 5
                            value: Math.round(((img && img.activeOpacity !== undefined) ? img.activeOpacity : 1.0) * 100)
                            textFromValue: (v) => (v / 100).toFixed(2)
                            valueFromText: (t) => Math.round(parseFloat(t) * 100)
                            onValueModified: if (img) backend.setImageActiveOpacity(img.id, value / 100)
                        }
                        Controls.Switch {
                            Kirigami.FormData.label: "Gaze attention:"
                            checked: !(img && img.attentionEnabled === false)
                            onToggled: if (img) backend.setImageAttention(img.id, checked)
                        }
                        Controls.Button {
                            Kirigami.FormData.label: " "
                            text: "Place in front of me"
                            enabled: backend.desktopRunning && backend.busy === ""
                            onClicked: if (img) backend.recenterImage(img.id)
                        }
                        Controls.Button {
                            Kirigami.FormData.label: " "
                            text: "Remove"
                            enabled: backend.busy === "" && images.length > 1
                            onClicked: {
                                if (img) backend.removeImageInstrument(img.id)
                                ipage.closeEdit()
                            }
                        }
                    }

                    // Launcher settings
                    Kirigami.FormLayout {
                        Layout.fillWidth: true
                        visible: editKey.indexOf("launcher:") === 0 && editLauncher
                        readonly property var ln: editLauncher

                        Controls.Label {
                            visible: !!(ln && ln.actionKind === "application" && ln.desktopId && ln.appAvailable === false)
                            Kirigami.FormData.label: " "
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            color: Kirigami.Theme.negativeTextColor
                            text: "Configured application is not available on this system."
                        }
                        Controls.ComboBox {
                            Kirigami.FormData.label: "Action type:"
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 14
                            model: [
                                { text: "Application", value: "application" },
                                { text: "Frametop action", value: "action" },
                                { text: "Custom command", value: "command" }
                            ]
                            textRole: "text"
                            valueRole: "value"
                            Component.onCompleted: currentIndex = Math.max(0, indexOfValue((ln && ln.actionKind) || "application"))
                            onActivated: {
                                if (!ln) return
                                if (currentValue === "application" && apps.length)
                                    backend.setLauncherDesktop(ln.id, apps[0].id)
                                else if (currentValue === "action" && actions.length)
                                    backend.setLauncherSemantic(ln.id, actions[0].id)
                            }
                        }
                        Controls.ComboBox {
                            visible: !ln || ln.actionKind === "application" || ln.actionKind === undefined
                            Kirigami.FormData.label: "Application:"
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 18
                            model: apps
                            textRole: "name"
                            valueRole: "id"
                            Component.onCompleted: {
                                const want = (ln && ln.desktopId) || ""
                                const i = indexOfValue(want)
                                currentIndex = i >= 0 ? i : 0
                            }
                            onActivated: if (ln) backend.setLauncherDesktop(ln.id, currentValue)
                        }
                        Controls.ComboBox {
                            visible: !!(ln && ln.actionKind === "action")
                            Kirigami.FormData.label: "Action:"
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 16
                            model: actions
                            textRole: "label"
                            valueRole: "id"
                            Component.onCompleted: {
                                const want = (ln && ln.semantic) || ""
                                const i = indexOfValue(want)
                                currentIndex = i >= 0 ? i : 0
                            }
                            onActivated: if (ln) backend.setLauncherSemantic(ln.id, currentValue)
                        }
                        Controls.TextField {
                            visible: !!(ln && ln.actionKind === "command")
                            Kirigami.FormData.label: "Command:"
                            Layout.fillWidth: true
                            placeholderText: ln && ln.commandShell ? "shell command" : "argv words"
                            text: (ln && ln.commandText) ? ln.commandText : ""
                            onEditingFinished: if (ln) backend.setLauncherCommand(ln.id, text, !!(ln && ln.commandShell))
                        }
                        Controls.Switch {
                            visible: !!(ln && ln.actionKind === "command")
                            Kirigami.FormData.label: "Run via shell:"
                            checked: !!(ln && ln.commandShell)
                            onToggled: if (ln) backend.setLauncherCommand(ln.id, (ln && ln.commandText) || "", checked)
                        }
                        Controls.ComboBox {
                            Kirigami.FormData.label: "Appearance:"
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 14
                            model: [
                                { text: "App icon", value: "app" },
                                { text: "Glyph", value: "glyph" },
                                { text: "Custom image", value: "image" },
                                { text: "Fallback", value: "fallback" }
                            ]
                            textRole: "text"
                            valueRole: "value"
                            Component.onCompleted: currentIndex = Math.max(0, indexOfValue((ln && ln.appearance) || "app"))
                            onActivated: {
                                if (!ln) return
                                if (currentValue === "glyph")
                                    backend.setLauncherAppearance(ln.id, "glyph", (ln && ln.glyph) || "star")
                                else if (currentValue === "app")
                                    backend.setLauncherAppearance(ln.id, "app", "")
                                else if (currentValue === "fallback")
                                    backend.setLauncherAppearance(ln.id, "fallback", "")
                            }
                        }
                        Controls.ComboBox {
                            visible: !!(ln && ln.appearance === "glyph")
                            Kirigami.FormData.label: "Glyph:"
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                            model: glyphs
                            Component.onCompleted: {
                                const want = (ln && ln.glyph) || "star"
                                const i = model.indexOf(want)
                                currentIndex = i >= 0 ? i : 0
                            }
                            onActivated: if (ln) backend.setLauncherAppearance(ln.id, "glyph", currentText)
                        }
                        Controls.Button {
                            visible: !!(ln && ln.appearance === "image")
                            Kirigami.FormData.label: " "
                            text: "Choose custom image…"
                            enabled: backend.busy === ""
                            onClicked: {
                                pendingLauncherFileId = ln.id
                                launcherFileDialog.open()
                            }
                        }
                        Controls.ComboBox {
                            Kirigami.FormData.label: "Anchor:"
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                            model: ipage.anchorChoices
                            textRole: "text"
                            valueRole: "value"
                            Component.onCompleted: currentIndex = Math.max(0, indexOfValue((ln && ln.anchor) || "world"))
                            onActivated: if (ln) backend.setLauncherAnchor(ln.id, currentValue)
                        }
                        Controls.SpinBox {
                            Kirigami.FormData.label: "Size (metres):"
                            from: 8; to: 120; stepSize: 2
                            value: Math.round(((ln && ln.metres !== undefined) ? ln.metres : 0.28) * 100)
                            textFromValue: (v) => (v / 100).toFixed(2)
                            valueFromText: (t) => Math.round(parseFloat(t) * 100)
                            onValueModified: if (ln) backend.setLauncherMetres(ln.id, value / 100)
                        }
                        Controls.SpinBox {
                            Kirigami.FormData.label: "Idle opacity:"
                            from: 0; to: 100; stepSize: 5
                            value: Math.round(((ln && ln.idleOpacity !== undefined) ? ln.idleOpacity : 0.55) * 100)
                            textFromValue: (v) => (v / 100).toFixed(2)
                            valueFromText: (t) => Math.round(parseFloat(t) * 100)
                            onValueModified: if (ln) backend.setLauncherIdleOpacity(ln.id, value / 100)
                        }
                        Controls.SpinBox {
                            Kirigami.FormData.label: "Active opacity:"
                            from: 0; to: 100; stepSize: 5
                            value: Math.round(((ln && ln.activeOpacity !== undefined) ? ln.activeOpacity : 1.0) * 100)
                            textFromValue: (v) => (v / 100).toFixed(2)
                            valueFromText: (t) => Math.round(parseFloat(t) * 100)
                            onValueModified: if (ln) backend.setLauncherActiveOpacity(ln.id, value / 100)
                        }
                        Controls.Switch {
                            Kirigami.FormData.label: "Gaze attention:"
                            checked: !(ln && ln.attentionEnabled === false)
                            onToggled: if (ln) backend.setLauncherAttention(ln.id, checked)
                        }
                        Controls.Button {
                            Kirigami.FormData.label: " "
                            text: "Place in front of me"
                            enabled: backend.desktopRunning && backend.busy === ""
                            onClicked: if (ln) backend.recenterLauncher(ln.id)
                        }
                        Controls.Button {
                            Kirigami.FormData.label: " "
                            text: "Test activate"
                            enabled: backend.busy === ""
                            onClicked: if (ln) backend.activateLauncher(ln.id)
                        }
                        Controls.Button {
                            Kirigami.FormData.label: " "
                            text: "Remove"
                            enabled: backend.busy === ""
                            onClicked: {
                                if (ln) backend.removeLauncherInstrument(ln.id)
                                ipage.closeEdit()
                            }
                        }
                    }
                }
            }

            FileDialog {
                id: imageFileDialog
                title: "Choose image for Spatial Instrument"
                fileMode: FileDialog.OpenFile
                nameFilters: [
                    "Images (*.png *.gif *.jpg *.jpeg)",
                    "All files (*)"
                ]
                onAccepted: backend.setImageFile(pendingImageId || "image", selectedFile.toString())
            }
            FileDialog {
                id: launcherFileDialog
                title: "Choose custom Launcher image"
                fileMode: FileDialog.OpenFile
                nameFilters: [
                    "Images (*.png *.gif *.jpg *.jpeg)",
                    "All files (*)"
                ]
                onAccepted: backend.setLauncherImageFile(pendingLauncherFileId || "launcher", selectedFile.toString())
            }
        }
    }

    // ---------------------------------------------------------------- Layout
    Component {
        id: layoutPage
        Kirigami.ScrollablePage {
            id: lpage
            title: "Layout"
            property var layout: backend.layout
            property var preset: layout.preset || {}
            property bool hasCustom: (layout.screens || []).some(s => s.pos !== undefined)

            actions: [
                Kirigami.Action {
                    text: "Arrange now"
                    icon.name: "view-restore"
                    tooltip: "Float the screens out of the dashboard and put them in this layout, around where you're facing"
                    enabled: backend.desktopRunning && backend.busy === ""
                    onTriggered: backend.arrange()
                },
                Kirigami.Action {
                    text: "Save current arrangement"
                    icon.name: "document-save"
                    tooltip: "Use where the screens are now (placed by hand) as the layout"
                    enabled: backend.desktopRunning && backend.busy === ""
                    onTriggered: backend.capture()
                }
            ]

            header: Kirigami.InlineMessage {
                position: Kirigami.InlineMessage.Position.Header
                visible: backend.busy !== ""
                type: Kirigami.MessageType.Information
                text: backend.busy + "… (the pointer is borrowed for a few seconds)"
            }

            ColumnLayout {
                spacing: Kirigami.Units.largeSpacing

                Kirigami.FormLayout {
                    Layout.fillWidth: true

                    Controls.ComboBox {
                        Kirigami.FormData.label: "Arrangement:"
                        model: [
                            { text: "Curved around you", value: "arc" },
                            { text: "Flat wall", value: "flat" },
                            { text: "Saved arrangement", value: "custom" }
                        ]
                        textRole: "text"
                        valueRole: "value"
                        currentIndex: lpage.layout.mode === "custom" ? 2 : (lpage.preset.kind === "flat" ? 1 : 0)
                        onActivated: {
                            if (currentValue === "custom") backend.setMode("custom")
                            else backend.setPreset("kind", currentValue)
                        }
                    }

                    Controls.Label {
                        visible: lpage.layout.mode === "custom"
                        Kirigami.FormData.label: ""
                        text: lpage.hasCustom ? "Where the screens were when you saved. Pick a preset to edit."
                                              : "Nothing saved yet: place the screens by hand, then Save current arrangement."
                        opacity: 0.7
                        wrapMode: Text.Wrap
                        Layout.maximumWidth: Kirigami.Units.gridUnit * 20
                    }

                    Controls.SpinBox {
                        Kirigami.FormData.label: "Rows:"
                        visible: lpage.layout.mode !== "custom"
                        from: 1
                        to: Math.max(1, backend.screens)
                        value: lpage.preset.rows || 1
                        onValueModified: backend.setPreset("rows", value)
                    }

                    Repeater {
                        model: [
                            { key: "distance", label: "Distance", from: 0.6, to: 3.0, step: 0.05, unit: "m", def: 1.2 },
                            { key: "gap", label: "Gap", from: 0.0, to: 0.3, step: 0.01, unit: "m", def: 0.04 },
                            { key: "height", label: "Height", from: -0.8, to: 0.8, step: 0.05, unit: "m", def: 0.0 }
                        ]
                        delegate: RowLayout {
                            required property var modelData
                            visible: lpage.layout.mode !== "custom"
                            Kirigami.FormData.label: modelData.label + ":"
                            Controls.Slider {
                                id: s
                                from: modelData.from; to: modelData.to; stepSize: modelData.step
                                value: lpage.preset[modelData.key] !== undefined ? lpage.preset[modelData.key] : modelData.def
                                Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                                onMoved: backend.setPreset(modelData.key, value)
                            }
                            Controls.Label {
                                text: (modelData.key === "height" && s.value > 0 ? "+" : "") + s.value.toFixed(2) + " " + modelData.unit
                                      + (modelData.key === "height" ? " (from eye level)" : "")
                            }
                        }
                    }

                    Controls.Switch {
                        Kirigami.FormData.label: "When the desktop starts:"
                        text: "Float the screens and arrange them"
                        checked: lpage.layout.auto !== false
                        onToggled: backend.setAuto(checked)
                    }
                }

                Kirigami.FormLayout {
                    Layout.fillWidth: true
                    visible: backend.backend === "screens"
                    Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: "Named profiles" }

                    Controls.ComboBox {
                        id: profilePick
                        Kirigami.FormData.label: "Profile:"
                        model: (backend.profiles.names || []).length ? backend.profiles.names : ["(none yet)"]
                        enabled: (backend.profiles.names || []).length > 0
                        Component.onCompleted: {
                            const cur = backend.profiles.current
                            if (cur) currentIndex = Math.max(0, model.indexOf(cur))
                        }
                        Connections {
                            target: backend
                            function onChanged() {
                                const names = backend.profiles.names || []
                                profilePick.model = names.length ? names : ["(none yet)"]
                                profilePick.enabled = names.length > 0
                                const cur = backend.profiles.current
                                if (cur && names.indexOf(cur) >= 0)
                                    profilePick.currentIndex = names.indexOf(cur)
                            }
                        }
                    }

                    Controls.TextField {
                        id: profileName
                        Kirigami.FormData.label: "Save as:"
                        placeholderText: "Desk, Cinema, HUD…"
                    }

                    RowLayout {
                        Kirigami.FormData.label: ""
                        Controls.Button {
                            text: "Apply"
                            enabled: backend.desktopRunning && backend.busy === "" && (backend.profiles.names || []).length > 0
                            onClicked: backend.applyProfile(profilePick.currentText)
                        }
                        Controls.Button {
                            text: "Save current as…"
                            enabled: backend.desktopRunning && backend.busy === "" && profileName.text.trim() !== ""
                            onClicked: backend.saveProfile(profileName.text.trim())
                        }
                        Controls.Button {
                            text: "Update selected"
                            enabled: backend.desktopRunning && backend.busy === "" && (backend.profiles.names || []).length > 0
                            onClicked: backend.saveProfile(profilePick.currentText)
                        }
                        Controls.Button {
                            text: "Delete"
                            enabled: backend.busy === "" && (backend.profiles.names || []).length > 0
                            onClicked: backend.deleteProfile(profilePick.currentText)
                        }
                    }

                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.7
                        text: "Profiles store the whole spatial workspace: screens (pose, width, curve, anchors, "
                              + "active/idle opacity, gaze attention) and Spatial Instruments (Clock, Date, Battery, "
                              + "Device storage, SD card, Media, Image, Launcher). "
                              + "They do not change screen count, resolution, or scale. CLI: ft-layout profile apply NAME"
                    }

                    Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: "Profile slots (VR chrome 1–6)" }

                    Repeater {
                        model: backend.profiles.slots || []
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            Controls.Label {
                                text: "Slot " + modelData.index + ":"
                                Layout.preferredWidth: Kirigami.Units.gridUnit * 4
                            }
                            Controls.ComboBox {
                                id: slotPick
                                Layout.fillWidth: true
                                model: ["(empty)"].concat(backend.profiles.names || [])
                                Component.onCompleted: {
                                    const names = backend.profiles.names || []
                                    currentIndex = modelData.profile && names.indexOf(modelData.profile) >= 0
                                        ? names.indexOf(modelData.profile) + 1 : 0
                                }
                                Connections {
                                    target: backend
                                    function onChanged() {
                                        const names = backend.profiles.names || []
                                        slotPick.model = ["(empty)"].concat(names)
                                        const cur = (backend.profiles.slots || [])[modelData.index - 1]
                                        const name = cur ? cur.profile : ""
                                        slotPick.currentIndex = name && names.indexOf(name) >= 0
                                            ? names.indexOf(name) + 1 : 0
                                    }
                                }
                                onActivated: {
                                    if (currentIndex <= 0)
                                        backend.clearProfileSlot(modelData.index)
                                    else
                                        backend.assignProfileSlot(modelData.index, currentText)
                                }
                            }
                            Controls.Button {
                                text: "Apply"
                                enabled: backend.desktopRunning && backend.busy === "" && modelData.profile !== ""
                                onClicked: backend.applyProfileSlot(modelData.index)
                            }
                            Controls.Label {
                                text: (backend.profiles.current_slot === modelData.index) ? "●" : ""
                                opacity: 0.8
                            }
                        }
                    }

                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.7
                        text: "Slots appear as numbered buttons under every screen in VR. Clicking a slot applies that "
                              + "profile to the whole workspace (450 ms transition). CLI: ft-layout profile slot 1 Desk"
                    }
                }

                // Preview: from above (you at the bottom) and from the front.
                Kirigami.Heading { level: 3; text: "Preview" }
                Canvas {
                    id: preview
                    Layout.fillWidth: true
                    Layout.preferredHeight: Kirigami.Units.gridUnit * 13
                    property var plan: backend.plan
                    onPlanChanged: requestPaint()
                    onWidthChanged: requestPaint()

                    onPaint: {
                        const ctx = getContext("2d")
                        ctx.reset()
                        const text = Kirigami.Theme.textColor
                        const accent = Kirigami.Theme.highlightColor
                        const half = width / 2
                        ctx.font = Kirigami.Theme.smallFont.pixelSize + "px sans-serif"
                        ctx.fillStyle = text
                        ctx.fillText("From above", 4, 12)
                        ctx.fillText("From the front", half + 8, 12)
                        if (!plan || plan.length === 0) return

                        // From above: x right, forward (-z) up; you are the dot at the bottom.
                        let ends = [[0, 0]]
                        for (const p of plan) {
                            const f = p.faceYaw * Math.PI / 180
                            const rx = Math.cos(f) * p.width / 2, rz = -Math.sin(f) * p.width / 2
                            ends.push([p.x - rx, p.z - rz], [p.x + rx, p.z + rz])
                        }
                        const xs = ends.map(e => e[0]), zs = ends.map(e => e[1])
                        const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...zs) - Math.min(...zs), 0.5)
                        const k = Math.min(half - 20, height - 44) / span
                        const cx = half / 2 - (Math.max(...xs) + Math.min(...xs)) / 2 * k
                        const cz = height - 12 - Math.max(...zs) * k  // your dot 12 px above the bottom
                        const P = (x, z) => [cx + x * k, cz + z * k]
                        ctx.fillStyle = text
                        ctx.beginPath(); const me = P(0, 0); ctx.arc(me[0], me[1], 4, 0, 2 * Math.PI); ctx.fill()
                        ctx.lineWidth = 4
                        ctx.lineCap = "round"
                        // Screens stacked in rows share a spot from above, so they share a label ("1·3"):
                        // the same direction on a curve, the same x on a flat wall.
                        const flat = plan.every(p => Math.abs(p.faceYaw - plan[0].faceYaw) < 0.1
                                                   && Math.abs(p.facePitch - plan[0].facePitch) < 0.1)
                        const labels = {}
                        for (const p of plan) {
                            const f = p.faceYaw * Math.PI / 180
                            const rx = Math.cos(f) * p.width / 2, rz = -Math.sin(f) * p.width / 2
                            const a = P(p.x - rx, p.z - rz), b = P(p.x + rx, p.z + rz)
                            ctx.strokeStyle = accent
                            ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke()
                            const c = P(p.x, p.z), spot = flat ? Math.round(p.x * 50) : Math.round(p.faceYaw * 2)
                            labels[spot] = labels[spot] || { at: c, names: [] }
                            labels[spot].names.push(p.index + 1)
                        }
                        ctx.fillStyle = text
                        for (const spot in labels) {
                            const l = labels[spot], t = l.names.join("·")
                            ctx.fillText(t, l.at[0] - ctx.measureText(t).width / 2, l.at[1] - 7)
                        }

                        // From the front: x right, y up. A flat wall as it is; a curved layout
                        // unrolled (arc length by yaw and pitch), so the gaps show true.
                        const front = plan.map(p => {
                            if (flat) return { x: p.x, y: p.y, w: p.width, h: p.height }
                            const r = Math.sqrt(p.x * p.x + p.y * p.y + p.z * p.z)
                            const arc = m => 2 * r * Math.atan(m / 2 / r)  // what the screen spans on the curve
                            return { x: -p.faceYaw * Math.PI / 180 * r, y: p.facePitch * Math.PI / 180 * r,
                                     w: arc(p.width), h: arc(p.height) }
                        })
                        const fx = [], fy = []
                        front.forEach(f => { fx.push(f.x - f.w / 2, f.x + f.w / 2); fy.push(f.y - f.h / 2, f.y + f.h / 2) })
                        fy.push(0)
                        const fspan = Math.max(Math.max(...fx) - Math.min(...fx), Math.max(...fy) - Math.min(...fy), 0.5)
                        const fk = Math.min(half - 20, height - 44) / fspan
                        const ox = half + half / 2 - (Math.max(...fx) + Math.min(...fx)) / 2 * fk
                        const oy = 30 + (height - 42) / 2 + (Math.max(...fy) + Math.min(...fy)) / 2 * fk
                        ctx.strokeStyle = Kirigami.Theme.disabledTextColor
                        ctx.lineWidth = 1
                        ctx.setLineDash([4, 4])
                        ctx.beginPath(); ctx.moveTo(half + 8, oy); ctx.lineTo(width - 4, oy); ctx.stroke()  // eye level
                        ctx.setLineDash([])
                        plan.forEach((p, i) => {
                            const f = front[i], x = ox + (f.x - f.w / 2) * fk, y = oy - (f.y + f.h / 2) * fk
                            ctx.fillStyle = Qt.rgba(accent.r, accent.g, accent.b, 0.35)
                            ctx.fillRect(x, y, f.w * fk, f.h * fk)
                            ctx.strokeStyle = accent
                            ctx.lineWidth = 2
                            ctx.strokeRect(x, y, f.w * fk, f.h * fk)
                            ctx.fillStyle = text
                            ctx.fillText(String(p.index + 1), x + f.w * fk / 2 - 3, y + f.h * fk / 2 + 4)
                        })
                    }
                }

                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "The layout goes around where you're facing when it's applied. Move screens by hand any time "
                          + "(grab bar under each screen); to put them back: Meta+Shift+R in the desktop, the Reset "
                          + "Screen Layout menu entry, Arrange now here, or a mouse button mapped to \"Reset desktop "
                          + "screen layout\" in Frametop Input Settings → Buttons."
                }
            }
        }
    }

    // ---------------------------------------------------------------- Visibility
    Component {
        id: visibilityPage
        Kirigami.ScrollablePage {
            id: vpage
            title: "Visibility"
            property var v: backend.visibility

            actions: [
                Kirigami.Action {
                    text: "Hide/show now"
                    icon.name: "view-visible"
                    enabled: backend.desktopRunning
                    onTriggered: backend.toggleScreens()
                }
            ]

            ColumnLayout {
                spacing: Kirigami.Units.largeSpacing

                Kirigami.FormLayout {
                    Layout.fillWidth: true

                    Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: "When the screens show" }

                    Repeater {
                        model: [
                            { value: "always", text: "Always", help: "Meta+Shift+H (or a mapped button) hides them. During VR games, see below." },
                            { value: "dashboard", text: "Only with the SteamVR dashboard open", help: "They come and go with the dashboard. Meta+Shift+H shows them anyway." },
                            { value: "except_dashboard", text: "Hide whenever the SteamVR dashboard opens", help: "Screens stay up normally, then tuck away when you open the dashboard so Steam UI has the view. Meta+Shift+H shows them anyway while the dashboard is open." },
                            { value: "gesture", text: "While I look at my wrist", help: "They show while you look toward the controller below. Meta+Shift+H shows them anyway." },
                            { value: "toggle", text: "Only when I show them", help: "Hidden until Meta+Shift+H (or a mapped button) shows them." }
                        ]
                        delegate: ColumnLayout {
                            required property var modelData
                            spacing: 0
                            Controls.RadioButton {
                                text: modelData.text
                                checked: vpage.v.mode === modelData.value
                                onToggled: if (checked) backend.setVisibility("mode", modelData.value)
                            }
                            Controls.Label {
                                text: modelData.help
                                opacity: 0.7
                                font: Kirigami.Theme.smallFont
                                leftPadding: Kirigami.Units.gridUnit * 1.6
                                wrapMode: Text.Wrap
                                Layout.maximumWidth: Kirigami.Units.gridUnit * 26
                            }
                        }
                    }

                    RowLayout {
                        Kirigami.FormData.label: "Wrist:"
                        visible: vpage.v.mode === "gesture"
                        Controls.ComboBox {
                            model: [{ text: "Left controller", value: "left" }, { text: "Right controller", value: "right" }]
                            textRole: "text"
                            valueRole: "value"
                            Component.onCompleted: currentIndex = indexOfValue(vpage.v.gesture_hand)
                            onActivated: backend.setVisibility("gesture_hand", currentValue)
                        }
                    }
                    RowLayout {
                        Kirigami.FormData.label: "Look within:"
                        visible: vpage.v.mode === "gesture"
                        Controls.Slider {
                            id: gesture
                            from: 5; to: 60; stepSize: 1
                            value: vpage.v.gesture_angle
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                            onMoved: backend.setVisibility("gesture_angle", value)
                        }
                        Controls.Label { text: Math.round(gesture.value) + "° of it" }
                    }

                    Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: "During VR games" }

                    Repeater {
                        model: [
                            { value: "hide", text: "Hide them unless the SteamVR dashboard is open", help: "The game has the view to itself; open the dashboard (or press Meta+Shift+H) to see the screens." },
                            { value: "visible", text: "Keep them visible over the game", help: "They float over the game as they are outside it." }
                        ]
                        delegate: ColumnLayout {
                            required property var modelData
                            spacing: 0
                            Controls.RadioButton {
                                text: modelData.text
                                enabled: vpage.v.mode === "always"
                                checked: (vpage.v.in_games || "hide") === modelData.value
                                onToggled: if (checked) backend.setVisibility("in_games", modelData.value)
                            }
                            Controls.Label {
                                text: modelData.help
                                opacity: 0.7
                                font: Kirigami.Theme.smallFont
                                leftPadding: Kirigami.Units.gridUnit * 1.6
                                wrapMode: Text.Wrap
                                Layout.maximumWidth: Kirigami.Units.gridUnit * 26
                            }
                        }
                    }
                    Controls.Label {
                        visible: vpage.v.mode !== "always"
                        text: "Applies when the screens show \"Always\"; the other choices above already keep them out of the way."
                        opacity: 0.7
                        font: Kirigami.Theme.smallFont
                        wrapMode: Text.Wrap
                        Layout.maximumWidth: Kirigami.Units.gridUnit * 26
                    }

                    Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: "Controllers on the screens" }

                    Repeater {
                        model: [
                            { value: "outside_games", text: "Except during VR games", help: "Over a VR game the screens stay up, but the controllers stay in the game. Use the 3D mouse, or open the SteamVR dashboard, to work the screens." },
                            { value: "always", text: "Always", help: "Controllers' lasers work the screens whenever they're visible, even over a VR game (which then can't use the controllers)." },
                            { value: "dashboard", text: "Only with the SteamVR dashboard open", help: "Otherwise only the 3D mouse works the screens. Also for flatscreen games, which don't count as VR games." }
                        ]
                        delegate: ColumnLayout {
                            required property var modelData
                            spacing: 0
                            Controls.RadioButton {
                                text: modelData.text
                                checked: (vpage.v.controllers || "outside_games") === modelData.value
                                onToggled: if (checked) backend.setVisibility("controllers", modelData.value)
                            }
                            Controls.Label {
                                text: modelData.help
                                opacity: 0.7
                                font: Kirigami.Theme.smallFont
                                leftPadding: Kirigami.Units.gridUnit * 1.6
                                wrapMode: Text.Wrap
                                Layout.maximumWidth: Kirigami.Units.gridUnit * 26
                            }
                        }
                    }

                    Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: "Screens on a wrist or head" }

                    RowLayout {
                        Kirigami.FormData.label: "Show while facing you within:"
                        Controls.Slider {
                            id: wrist
                            from: 20; to: 120; stepSize: 1
                            value: vpage.v.wrist_angle
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                            onMoved: backend.setVisibility("wrist_angle", value)
                        }
                        Controls.Label { text: Math.round(wrist.value) + "°" }
                    }
                    RowLayout {
                        Kirigami.FormData.label: "All screens:"
                        Controls.Button {
                            text: "Pin to left wrist"
                            enabled: backend.desktopRunning
                            onClicked: backend.pinAll("left")
                        }
                        Controls.Button {
                            text: "Pin to right wrist"
                            enabled: backend.desktopRunning
                            onClicked: backend.pinAll("right")
                        }
                        Controls.Button {
                            text: "Pin to head (soft)"
                            enabled: backend.desktopRunning
                            onClicked: backend.pinAll("head")
                        }
                        Controls.Button {
                            text: "Yaw follow"
                            enabled: backend.desktopRunning
                            onClicked: backend.pinAll("yaw-follow")
                        }
                        Controls.Button {
                            text: "Position follow"
                            enabled: backend.desktopRunning
                            onClicked: backend.pinAll("position-follow")
                        }
                        Controls.Button {
                            text: "Unpin"
                            enabled: backend.desktopRunning
                            onClicked: backend.unpinAll()
                        }
                    }
                }

                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "Pin one screen: carry it by its bar and sweep its laser across your other controller. A "
                          + "ring shows the target and a dot shows where the laser is; crossing the ring arms the pin (ring "
                          + "and bar turn blue), crossing it again disarms it. Turn and place the screen the way you want, "
                          + "then let go: it rides on that wrist at that size and distance, however far away. To adjust a "
                          + "pinned screen, grab its bar, move it, and let go (it stays pinned); sweep across the ring to "
                          + "take it off. Wrist-pinned screens show while you see their front within the angle above. "
                          + "Head (soft) follows the headset with a short lag; yaw-follow turns with you but stays upright; "
                          + "position-follow walks with you without rotating. Per-screen Follow dead zone lets you glance "
                          + "at a corner without the panel chasing (past the angle it follows again). "
                          + "Use the anchor button under each screen to cycle "
                          + "modes, or CLI: ft-layout pin 1 head. Save current arrangement / a named profile keeps anchors."
                }
            }
        }
    }

    // ------------------------------------------------------------- Background
    Component {
        id: backgroundPage
        Kirigami.ScrollablePage {
            id: bpage
            title: "Background"

            actions: [
                Kirigami.Action {
                    text: "Refresh"
                    icon.name: "view-refresh"
                    enabled: backend.busy === ""
                    onTriggered: backend.refreshBackground()
                },
                Kirigami.Action {
                    text: "Open folder"
                    icon.name: "folder-open"
                    onTriggered: backend.openBackgroundDirectory()
                }
            ]

            Component.onCompleted: backend.refreshBackground()

            // QML portal FileDialog ignores currentFolder (opens ~). Use QtWidgets picker.
            function openBackgroundPicker() {
                backend.pickBackgroundFile()
            }

            ColumnLayout {
                width: parent.width
                spacing: Kirigami.Units.largeSpacing

                Kirigami.InlineMessage {
                    Layout.fillWidth: true
                    visible: backend.backgroundError !== ""
                    type: Kirigami.MessageType.Warning
                    text: backend.backgroundError
                          + " — SteamVR must be running. CLI: scripts/frame-background status"
                }

                Kirigami.FormLayout {
                    Layout.fillWidth: true

                    Kirigami.Separator {
                        Kirigami.FormData.isSection: true
                        Kirigami.FormData.label: "SteamVR environment"
                    }

                    Controls.Label {
                        Kirigami.FormData.label: "Mode:"
                        text: backend.backgroundMode === "aurora" ? "Aurora (procedural)"
                              : backend.backgroundMode === "image" ? "Image (360° skybox)"
                              : (backend.backgroundMode || "—")
                    }
                    Controls.Label {
                        Kirigami.FormData.label: "Current file:"
                        Layout.fillWidth: true
                        elide: Text.ElideMiddle
                        text: backend.backgroundMode === "aurora" ? "(Aurora — no image file)"
                              : (backend.backgroundFileName || "(none)")
                        opacity: backend.backgroundFileName || backend.backgroundMode === "aurora" ? 1.0 : 0.6
                    }
                    Controls.Label {
                        visible: backend.backgroundSizeText !== ""
                        Kirigami.FormData.label: "Size:"
                        text: backend.backgroundSizeText
                    }
                    Controls.Label {
                        visible: backend.backgroundPath !== "" && backend.backgroundMode === "image"
                        Kirigami.FormData.label: "Path:"
                        Layout.fillWidth: true
                        wrapMode: Text.WrapAnywhere
                        font: Kirigami.Theme.smallFont
                        opacity: 0.75
                        text: backend.backgroundPath
                    }

                    Kirigami.Separator {
                        Kirigami.FormData.isSection: true
                        Kirigami.FormData.label: "Choose"
                    }

                    Repeater {
                        model: backend.backgroundPresets
                        delegate: Controls.RadioButton {
                            required property var modelData
                            Kirigami.FormData.label: index === 0 ? "Preset:" : " "
                            text: modelData.text
                            checked: backend.backgroundPreset === modelData.id
                            enabled: backend.busy === ""
                            onToggled: if (checked) backend.setBackgroundPreset(modelData.id)
                        }
                    }

                    Controls.RadioButton {
                        Kirigami.FormData.label: " "
                        text: "Custom image…"
                        checked: backend.backgroundPreset === "custom"
                        enabled: backend.busy === ""
                        // Selecting the radio alone does not open the dialog; use the button.
                        onToggled: if (checked && backend.backgroundPreset !== "custom")
                                       bpage.openBackgroundPicker()
                    }

                    Controls.Button {
                        Kirigami.FormData.label: " "
                        text: "Choose equirectangular image…"
                        enabled: backend.busy === ""
                        onClicked: bpage.openBackgroundPicker()
                    }
                    Controls.Button {
                        Kirigami.FormData.label: " "
                        text: "Open backgrounds folder"
                        icon.name: "folder-open"
                        onClicked: backend.openBackgroundDirectory()
                    }
                    Controls.Label {
                        Kirigami.FormData.label: "Folder:"
                        Layout.fillWidth: true
                        wrapMode: Text.WrapAnywhere
                        font: Kirigami.Theme.smallFont
                        opacity: 0.75
                        text: backend.backgroundDirectory
                    }
                }

                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "This is SteamVR’s passive sky behind the dashboard (not SteamVR Home, not Frametop screens). "
                          + "Aurora is Valve’s procedural environment. Image mode loads a 360° equirectangular "
                          + "texture (about 2:1, e.g. 2048×1024 or 4096×2048). Custom files (PNG/JPEG/WebP/HDR/EXR) "
                          + "are converted to 8-bit PNG under ~/.config/openvr/config/frametop-backgrounds/ "
                          + "(HDR is tonemapped to SDR). Opaque Room View / passthrough "
                          + "can cover the skybox while it is on. CLI: scripts/frame-background set PATH"
                }
            }
        }
    }
}
