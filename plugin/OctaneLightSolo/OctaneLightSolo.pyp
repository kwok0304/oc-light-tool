"""Octane Light Solo for Cinema 4D 2026.2.

Dependency-free Python plugin for managing Octane light visibility, power and
color from a compact native Cinema 4D panel.
"""

import c4d
from c4d import gui, plugins


# Replace these IDs with IDs registered to you at Plugin Café before publishing.
PLUGIN_BASE = 1059870
PLUGIN_VERSION = "1.0.0"
CMD_SOLO_SELECTED = PLUGIN_BASE + 1
CMD_SOLO_ALL = PLUGIN_BASE + 2
CMD_BRIGHTNESS = PLUGIN_BASE + 3
CMD_COLOR = PLUGIN_BASE + 4
CMD_MANAGER = PLUGIN_BASE + 5

# IDs verified against the installed OctaneRenderStudio+ 1.9.3 resources.
OCTANE_LIGHT_POWER = 1151
OCTANE_DAYLIGHT_POWER = 1231
OCTANE_USE_LIGHT_COLOR = 1160
OCTANE_CAMERA_VISIBILITY_LEGACY = 1163
# DescID exported from OctaneRenderStudio+ 1.9.3 under C4D 2026.3.
OCTANE_CAMERA_VISIBILITY_2026 = 2026300

# Native Cinema 4D icon IDs selected from MaxonAssets.db.
ICON_SOLO = 12499
ICON_CAMERA_VISIBILITY = 5136

UI_POWER_AREA = 2001
UI_POWER_DOWN = 2002
UI_POWER_UP = 2003
UI_POWER_CLOSE = 2004

UI_COLOR_NAME = 3001
UI_COLOR_FIELD = 3002
UI_COLOR_WHITE = 3003
UI_COLOR_WARM = 3004
UI_COLOR_COOL = 3005
UI_COLOR_RED = 3006
UI_COLOR_GREEN = 3007
UI_COLOR_BLUE = 3008
UI_COLOR_CLOSE = 3009

UI_MANAGER_LIGHT = 4001
UI_MANAGER_REFRESH = 4002
UI_MANAGER_SELECT = 4003
UI_MANAGER_SOLO = 4004
UI_MANAGER_DEFAULT = 4005
UI_MANAGER_POWER_AREA = 4006
UI_MANAGER_POWER_DOWN = 4007
UI_MANAGER_POWER_UP = 4008
UI_MANAGER_COLOR = 4009
UI_MANAGER_WHITE = 4010
UI_MANAGER_WARM = 4011
UI_MANAGER_COOL = 4012
UI_MANAGER_CLOSE = 4013

UI_GROUP_SOLO_SELECTED = 4201
UI_GROUP_DEFAULT_ALL = 4202
UI_GROUP_REFRESH = 4203
UI_GROUP_SCROLL = 4204
UI_GROUP_ROWS = 4205
UI_GROUP_STATUS = 4206
ROW_CONTROL_BASE = 10000
ROW_CONTROL_STRIDE = 10


def _debug_log(*_args, **_kwargs):
    """Intentionally silent in the release build."""
    return None


def _iter_objects(node):
    """Yield all objects in a document hierarchy."""
    while node:
        yield node
        child = node.GetDown()
        if child:
            yield from _iter_objects(child)
        node = node.GetNext()


def _tag_text(tag):
    return " ".join((tag.GetName() or "", str(tag.GetType()))).lower()


def _is_octane_light(obj):
    """Best-effort detection without importing Octane's private Python API."""
    if obj is None:
        return False

    # Regular Octane lights are C4D light objects with an Octane light tag.
    is_c4d_light = obj.GetType() == c4d.Olight
    tags = list(obj.GetTags())
    tag_text = " ".join(_tag_text(tag) for tag in tags)
    name_text = (obj.GetName() or "").lower()

    # Some Octane builds expose a public symbol; use it when available.
    octane_tag_type = getattr(c4d, "OCTANE_LIGHT_TAG", None)
    if octane_tag_type is not None and any(tag.GetType() == octane_tag_type for tag in tags):
        return True

    if is_c4d_light and any(word in tag_text for word in
                            ("octane", "light tag", "ies", "daylight", "environment")):
        return True

    # Fallback for Octane environment/light objects whose tag IDs vary by build.
    return any(word in name_text for word in
               ("octane light", "octane sky", "octane daylight", "hdr environment",
                "hdri environment", "ies light"))


def _get_lights(doc):
    return [obj for obj in _iter_objects(doc.GetFirstObject()) if _is_octane_light(obj)]


def _get_render_visibility(obj):
    try:
        return obj[c4d.ID_BASEOBJECT_VISIBILITY_RENDER]
    except Exception:
        return None


def _set_render_visibility(obj, value):
    try:
        obj[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = value
        return True
    except Exception:
        return False


def _description_name(tag, parameter_id):
    """Return a localized parameter name for a first-level DescID."""
    try:
        description = tag.GetDescription(c4d.DESCFLAGS_DESC_0)
        for bc, desc_id, _group_id in description:
            if desc_id.GetDepth() and desc_id[0].id == parameter_id:
                return bc.GetString(c4d.DESC_NAME).strip().lower()
    except Exception:
        pass
    return ""


def _get_power_target(obj):
    """Return (tag, parameter id, value, maximum), or None."""
    if obj is None or not _is_octane_light(obj):
        return None

    # Description names are checked so unrelated tags with the same numeric ID
    # cannot accidentally be edited.
    for tag in obj.GetTags():
        for parameter_id, maximum in ((OCTANE_LIGHT_POWER, 100000.0),
                                      (OCTANE_DAYLIGHT_POWER, 1000.0)):
            name = _description_name(tag, parameter_id)
            if name not in ("power", "功率"):
                continue
            try:
                value = tag[parameter_id]
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    name_text = (obj.GetName() or "").lower()
                    if (parameter_id == OCTANE_LIGHT_POWER and
                            any(word in name_text for word in
                                ("environment", "octane sky", "hdr", "hdri"))):
                        maximum = 1000.0
                    return tag, parameter_id, float(value), maximum
            except Exception:
                continue
    return None


def _change_power(doc, obj, direction, qualifier=0):
    target = _get_power_target(obj)
    if target is None:
        return None

    tag, parameter_id, current, maximum = target
    if qualifier & c4d.QSHIFT:
        factor = 1.02
    elif qualifier & c4d.QCTRL:
        factor = 1.25
    else:
        factor = 1.10

    base = current if current > 0.0 else 0.0001
    value = base * factor if direction > 0 else base / factor
    value = max(0.0001, min(maximum, value))

    doc.StartUndo()
    doc.AddUndo(c4d.UNDOTYPE_CHANGE, tag)
    tag[parameter_id] = value
    tag.Message(c4d.MSG_UPDATE)
    doc.EndUndo()
    c4d.EventAdd()
    return value


def _set_power_value(doc, obj, value):
    target = _get_power_target(obj)
    if target is None:
        return False
    tag, parameter_id, _current, maximum = target
    value = max(0.0001, min(maximum, float(value)))
    doc.StartUndo()
    doc.AddUndo(c4d.UNDOTYPE_CHANGE, tag)
    tag[parameter_id] = value
    tag.Message(c4d.MSG_UPDATE)
    doc.EndUndo()
    c4d.EventAdd()
    return True


def _is_environment_light(obj):
    target = _get_power_target(obj)
    if target is not None and target[1] == OCTANE_DAYLIGHT_POWER:
        return True
    name = (obj.GetName() or "").lower() if obj else ""
    return any(word in name for word in
               ("daylight", "environment", "octane sky", "hdr", "hdri"))


def _get_color_target(obj):
    """Return the Octane light tag which supports C4D's native light color."""
    if obj is None or obj.GetType() != c4d.Olight or not _is_octane_light(obj):
        return None
    for tag in obj.GetTags():
        name = _description_name(tag, OCTANE_USE_LIGHT_COLOR)
        if name in ("use light color", "使用灯光颜色"):
            return tag
    return None


def _format_desc_id(desc_id):
    if isinstance(desc_id, int):
        return str(desc_id)
    try:
        levels = []
        for index in range(desc_id.GetDepth()):
            level = desc_id[index]
            levels.append(f"{level.id}:{level.dtype}:{level.creator}")
        return "/".join(levels)
    except Exception:
        return repr(desc_id)


def _read_parameter(tag, desc_id):
    if isinstance(desc_id, int):
        try:
            return tag[desc_id]
        except Exception:
            desc_id = c4d.DescID(c4d.DescLevel(desc_id))
    return tag.GetParameter(desc_id, c4d.DESCFLAGS_GET_0)


def _is_boolean_value(value):
    return isinstance(value, bool) or (isinstance(value, int) and value in (0, 1))


def _get_camera_visibility_target(obj, debug=False):
    """Return (Octane light tag, full DescID/ID, current state), or None."""
    if obj is None or not _is_octane_light(obj):
        return None

    accepted_names = {"camera visibility", "摄像机可见", "摄像机可见性"}
    for tag in obj.GetTags():
        # Octane 2026 can expose a generated DescID which differs from the
        # legacy ID in OctaneLightTag.h. Resolve the full live description
        # first so nested/generated parameters work as shown in the UI.
        try:
            description = tag.GetDescription(c4d.DESCFLAGS_DESC_0)
            for bc, desc_id, _group_id in description:
                name = bc.GetString(c4d.DESC_NAME).strip().lower()
                name_matches = (name in accepted_names or
                                ("camera" in name and "visib" in name) or
                                ("摄像机" in name and "可见" in name))
                if debug and ("visib" in name or "camera" in name or "可见" in name):
                    _debug_log(f"[OctaneLightSolo] candidate tag={tag.GetName()!r} "
                          f"name={name!r} desc={_format_desc_id(desc_id)}")
                if not name_matches:
                    continue
                value = _read_parameter(tag, desc_id)
                if _is_boolean_value(value):
                    if debug:
                        _debug_log(f"[OctaneLightSolo] camera parameter resolved from "
                              f"description: {_format_desc_id(desc_id)}, value={bool(value)}")
                    return tag, desc_id, value
        except Exception as error:
            if debug:
                _debug_log(f"[OctaneLightSolo] description scan failed for "
                      f"tag={tag.GetName()!r}: {error!r}")

        # Fallbacks for builds where the generated description is unavailable.
        exported_desc_id = c4d.DescID(c4d.DescLevel(
            OCTANE_CAMERA_VISIBILITY_2026, 15, 1))
        for parameter_id in (exported_desc_id,
                             OCTANE_CAMERA_VISIBILITY_2026,
                             OCTANE_CAMERA_VISIBILITY_LEGACY):
            try:
                value = _read_parameter(tag, parameter_id)
                if _is_boolean_value(value):
                    if debug:
                        _debug_log(f"[OctaneLightSolo] camera parameter resolved from "
                              f"fallback: {_format_desc_id(parameter_id)}, value={bool(value)}")
                    return tag, parameter_id, value
            except Exception as error:
                if debug:
                    _debug_log(f"[OctaneLightSolo] fallback "
                          f"{_format_desc_id(parameter_id)} failed on "
                          f"tag={tag.GetName()!r}: {error!r}")
                continue
    if debug:
        _debug_log(f"[OctaneLightSolo] camera parameter not found for {obj.GetName()!r}")
    return None


def _set_camera_visibility(doc, obj, value, target=None, debug=False):
    target = target or _get_camera_visibility_target(obj, debug=debug)
    if target is None:
        return False
    tag, parameter_id, _current = target
    doc.StartUndo()
    doc.AddUndo(c4d.UNDOTYPE_CHANGE, tag)
    try:
        desc_id = parameter_id
        if isinstance(desc_id, int):
            desc_id = c4d.DescID(c4d.DescLevel(desc_id))
        success = tag.SetParameter(desc_id, bool(value), c4d.DESCFLAGS_SET_0)
        if not success:
            raise RuntimeError("SetParameter returned False")
        tag.Message(c4d.MSG_UPDATE)
    except Exception as error:
        if debug:
            _debug_log(f"[OctaneLightSolo] camera SetParameter failed: "
                  f"desc={_format_desc_id(parameter_id)}, error={error!r}")
        return False
    finally:
        doc.EndUndo()
    c4d.EventAdd()
    if debug:
        try:
            actual = _read_parameter(tag, parameter_id)
        except Exception as error:
            actual = f"readback failed: {error!r}"
        _debug_log(f"[OctaneLightSolo] camera visibility changed: "
              f"object={obj.GetName()!r}, desc={_format_desc_id(parameter_id)}, "
              f"old={bool(_current)}, requested={bool(value)}, readback={actual}")
    return True


def _set_light_color(doc, obj, color):
    tag = _get_color_target(obj)
    if tag is None:
        return False

    color = c4d.Vector(max(0.0, min(1.0, color.x)),
                       max(0.0, min(1.0, color.y)),
                       max(0.0, min(1.0, color.z)))
    doc.StartUndo()
    doc.AddUndo(c4d.UNDOTYPE_CHANGE, obj)
    doc.AddUndo(c4d.UNDOTYPE_CHANGE, tag)
    obj[c4d.LIGHT_COLOR] = color
    tag[OCTANE_USE_LIGHT_COLOR] = True
    obj.Message(c4d.MSG_UPDATE)
    tag.Message(c4d.MSG_UPDATE)
    doc.EndUndo()
    c4d.EventAdd()
    return True


def _solo(doc, selected):
    lights = _get_lights(doc)
    if not lights:
        gui.MessageDialog("场景中没有识别到 Octane 灯光。\n请确认灯光带有 Octane Light Tag。")
        return

    selected_objects = selected if isinstance(selected, (list, tuple)) else [selected]
    selected_lights = [obj for obj in lights if obj in selected_objects]
    if not selected_lights:
        gui.MessageDialog("请先选择一个或多个 Octane 灯光对象。")
        return

    for obj in lights:
        # MODE_UNDEF is Cinema 4D's grey "Default" traffic-light state.
        _set_render_visibility(obj, c4d.MODE_UNDEF if obj in selected_lights else c4d.MODE_OFF)
    c4d.EventAdd()


def _solo_all(doc):
    lights = _get_lights(doc)
    if not lights:
        gui.MessageDialog("场景中没有识别到 Octane 灯光。")
        return
    for obj in lights:
        _set_render_visibility(obj, c4d.MODE_UNDEF)
    c4d.EventAdd()


class SoloSelectedCommand(plugins.CommandData):
    def Execute(self, doc):
        _solo(doc, doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_0))
        return True

    def GetState(self, doc):
        return c4d.CMD_ENABLED if doc and doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_0) else 0


class SoloAllCommand(plugins.CommandData):
    def Execute(self, doc):
        _solo_all(doc)
        return True


class BrightnessArea(gui.GeUserArea):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.object_name = "未选择 Octane 灯光"
        self.power = None

    def SetDisplay(self, object_name, power):
        self.object_name = object_name
        self.power = power
        self.Redraw()

    def GetMinSize(self):
        return 330, 105

    def DrawMsg(self, x1, y1, x2, y2, msg):
        self.OffScreenOn()
        self.DrawSetPen(c4d.Vector(0.12, 0.12, 0.12))
        self.DrawRectangle(x1, y1, x2, y2)

        self.DrawSetPen(c4d.Vector(0.90, 0.90, 0.90))
        self.DrawSetFont(c4d.FONT_BOLD)
        self.DrawText(self.object_name, 14, 12)

        if self.power is None:
            value_text = "功率：不可用"
        elif self.power >= 1000.0:
            value_text = f"功率：{self.power:,.1f}"
        elif self.power >= 10.0:
            value_text = f"功率：{self.power:.2f}"
        else:
            value_text = f"功率：{self.power:.4f}"

        self.DrawSetPen(c4d.Vector(0.55, 0.75, 1.00))
        self.DrawSetFont(c4d.FONT_BIG_BOLD)
        self.DrawText(value_text, 14, 38)

        self.DrawSetPen(c4d.Vector(0.68, 0.68, 0.68))
        self.DrawSetFont(c4d.FONT_DEFAULT)
        self.DrawText("在此区域滚轮调节 · Shift 精调 · Ctrl 快调", 14, 76)

    def InputEvent(self, msg):
        if (msg.GetInt32(c4d.BFM_INPUT_DEVICE) == c4d.BFM_INPUT_MOUSE and
                msg.GetInt32(c4d.BFM_INPUT_CHANNEL) == c4d.BFM_INPUT_MOUSEWHEEL):
            value = msg.GetFloat(c4d.BFM_INPUT_VALUE)
            if value == 0.0:
                value = float(msg.GetInt32(c4d.BFM_INPUT_VALUE))
            if value != 0.0:
                qualifier = msg.GetInt32(c4d.BFM_INPUT_QUALIFIER)
                self.owner.AdjustPower(1 if value > 0.0 else -1, qualifier)
            return True
        return False


class BrightnessDialog(gui.GeDialog):
    def __init__(self):
        super().__init__()
        self.area = BrightnessArea(self)

    def CreateLayout(self):
        self.SetTitle("Octane 灯光亮度滚轮")
        self.AddUserArea(UI_POWER_AREA, c4d.BFH_SCALE | c4d.BFV_SCALE,
                         initw=330, inith=105)
        self.AttachUserArea(self.area, UI_POWER_AREA)

        self.GroupBegin(2100, c4d.BFH_SCALE, cols=3)
        self.AddButton(UI_POWER_DOWN, c4d.BFH_SCALE, name="降低 10%")
        self.AddButton(UI_POWER_UP, c4d.BFH_SCALE, name="提高 10%")
        self.AddButton(UI_POWER_CLOSE, c4d.BFH_SCALE, name="关闭")
        self.GroupEnd()
        return True

    def InitValues(self):
        self.SetTimer(250)
        self.RefreshDisplay()
        return True

    def RefreshDisplay(self):
        doc = c4d.documents.GetActiveDocument()
        obj = doc.GetActiveObject() if doc else None
        target = _get_power_target(obj)
        if obj is None or target is None:
            self.area.SetDisplay("请选择带 Octane 灯光标签的灯光", None)
            return
        self.area.SetDisplay(obj.GetName(), target[2])

    def AdjustPower(self, direction, qualifier=0):
        doc = c4d.documents.GetActiveDocument()
        obj = doc.GetActiveObject() if doc else None
        value = _change_power(doc, obj, direction, qualifier) if doc else None
        if value is None:
            self.RefreshDisplay()
            return
        self.area.SetDisplay(obj.GetName(), value)

    def Command(self, command_id, msg):
        if command_id == UI_POWER_DOWN:
            self.AdjustPower(-1)
            return True
        if command_id == UI_POWER_UP:
            self.AdjustPower(1)
            return True
        if command_id == UI_POWER_CLOSE:
            self.Close()
            return True
        return True

    def Timer(self, msg):
        self.RefreshDisplay()

    def AskClose(self):
        self.SetTimer(0)
        return False


_brightness_dialog = BrightnessDialog()


class BrightnessCommand(plugins.CommandData):
    def Execute(self, doc):
        obj = doc.GetActiveObject() if doc else None
        if _get_power_target(obj) is None:
            gui.MessageDialog("请先选中带有 Octane 灯光标签的灯光对象。")
            return True
        _brightness_dialog.RefreshDisplay()
        return _brightness_dialog.Open(c4d.DLG_TYPE_ASYNC,
                                       pluginid=CMD_BRIGHTNESS,
                                       xpos=-1, ypos=-1,
                                       defaultw=350, defaulth=145)

    def RestoreLayout(self, secret):
        return _brightness_dialog.Restore(CMD_BRIGHTNESS, secret)

    def GetState(self, doc):
        return c4d.CMD_ENABLED if doc and doc.GetActiveObject() else 0


class ColorDialog(gui.GeDialog):
    COLOR_FLAGS = (c4d.DR_COLORFIELD_ENABLE_COLORWHEEL |
                   c4d.DR_COLORFIELD_ENABLE_HSV |
                   c4d.DR_COLORFIELD_ENABLE_RGB |
                   c4d.DR_COLORFIELD_ENABLE_KELVIN |
                   c4d.DR_COLORFIELD_ENABLE_SWATCHES |
                   c4d.DR_COLORFIELD_ICC_BASEDOC)

    def __init__(self):
        super().__init__()
        self.bound_object = None

    def CreateLayout(self):
        self.SetTitle("Octane 灯光颜色快捷调节")
        self.AddStaticText(UI_COLOR_NAME, c4d.BFH_SCALE,
                           name="请选择 Octane 灯光")
        self.AddColorField(UI_COLOR_FIELD, c4d.BFH_SCALE,
                           initw=360, inith=34,
                           colorflags=self.COLOR_FLAGS)

        self.GroupBegin(3100, c4d.BFH_SCALE, cols=6)
        self.AddButton(UI_COLOR_WHITE, c4d.BFH_SCALE, name="白色")
        self.AddButton(UI_COLOR_WARM, c4d.BFH_SCALE, name="暖色")
        self.AddButton(UI_COLOR_COOL, c4d.BFH_SCALE, name="冷色")
        self.AddButton(UI_COLOR_RED, c4d.BFH_SCALE, name="红色")
        self.AddButton(UI_COLOR_GREEN, c4d.BFH_SCALE, name="绿色")
        self.AddButton(UI_COLOR_BLUE, c4d.BFH_SCALE, name="蓝色")
        self.GroupEnd()

        self.AddButton(UI_COLOR_CLOSE, c4d.BFH_RIGHT, name="关闭")
        return True

    def InitValues(self):
        self.SetTimer(250)
        self.RefreshTarget(force=True)
        return True

    def RefreshTarget(self, force=False):
        doc = c4d.documents.GetActiveDocument()
        obj = doc.GetActiveObject() if doc else None
        if not force and obj == self.bound_object:
            return

        self.bound_object = obj
        valid = obj is not None and _get_color_target(obj) is not None
        self.Enable(UI_COLOR_FIELD, valid)
        if not valid:
            self.SetString(UI_COLOR_NAME, "请选择普通 Octane 灯光或 IES 灯光")
            return

        self.SetString(UI_COLOR_NAME, obj.GetName())
        color = obj[c4d.LIGHT_COLOR]
        self.SetColorField(UI_COLOR_FIELD, color, 1.0, 1.0,
                           self.COLOR_FLAGS)

    def ApplyColor(self, color):
        doc = c4d.documents.GetActiveDocument()
        obj = doc.GetActiveObject() if doc else None
        if doc is None or not _set_light_color(doc, obj, color):
            self.RefreshTarget(force=True)
            return
        self.bound_object = obj

    def ApplyPreset(self, color):
        self.SetColorField(UI_COLOR_FIELD, color, 1.0, 1.0,
                           self.COLOR_FLAGS)
        self.ApplyColor(color)

    def Command(self, command_id, msg):
        if command_id == UI_COLOR_FIELD:
            data = self.GetColorField(UI_COLOR_FIELD)
            if data:
                color = data.get("color", c4d.Vector(1.0))
                brightness = float(data.get("brightness", 1.0))
                self.ApplyColor(color * brightness)
            return True

        presets = {
            UI_COLOR_WHITE: c4d.Vector(1.0, 1.0, 1.0),
            UI_COLOR_WARM: c4d.Vector(1.0, 0.55, 0.25),
            UI_COLOR_COOL: c4d.Vector(0.45, 0.68, 1.0),
            UI_COLOR_RED: c4d.Vector(1.0, 0.05, 0.03),
            UI_COLOR_GREEN: c4d.Vector(0.05, 1.0, 0.08),
            UI_COLOR_BLUE: c4d.Vector(0.03, 0.15, 1.0),
        }
        if command_id in presets:
            self.ApplyPreset(presets[command_id])
            return True
        if command_id == UI_COLOR_CLOSE:
            self.Close()
            return True
        return True

    def Timer(self, msg):
        self.RefreshTarget()

    def AskClose(self):
        self.SetTimer(0)
        return False


_color_dialog = ColorDialog()


class ColorCommand(plugins.CommandData):
    def Execute(self, doc):
        obj = doc.GetActiveObject() if doc else None
        if _get_color_target(obj) is None:
            gui.MessageDialog("请先选中普通 Octane 灯光或 IES 灯光对象。")
            return True
        _color_dialog.RefreshTarget(force=True)
        return _color_dialog.Open(c4d.DLG_TYPE_ASYNC,
                                  pluginid=CMD_COLOR,
                                  xpos=-1, ypos=-1,
                                  defaultw=390, defaulth=145)

    def RestoreLayout(self, secret):
        return _color_dialog.Restore(CMD_COLOR, secret)

    def GetState(self, doc):
        return c4d.CMD_ENABLED if doc and doc.GetActiveObject() else 0


class LightManagerDialog(gui.GeDialog):
    COLOR_FLAGS = ColorDialog.COLOR_FLAGS

    def __init__(self):
        super().__init__()
        self.lights = []
        self.power_area = BrightnessArea(self)
        self.color_object = None

    def CreateLayout(self):
        self.SetTitle("Octane 灯光管理器")

        self.GroupBegin(4100, c4d.BFH_SCALE, cols=2)
        self.AddComboBox(UI_MANAGER_LIGHT, c4d.BFH_SCALE,
                         initw=310, allowfiltering=True)
        self.AddButton(UI_MANAGER_REFRESH, c4d.BFH_RIGHT, name="刷新")
        self.GroupEnd()

        self.GroupBegin(4101, c4d.BFH_SCALE, cols=3)
        self.AddButton(UI_MANAGER_SELECT, c4d.BFH_SCALE, name="选中对象")
        self.AddButton(UI_MANAGER_SOLO, c4d.BFH_SCALE, name="独显当前灯光")
        self.AddButton(UI_MANAGER_DEFAULT, c4d.BFH_SCALE, name="全部恢复默认")
        self.GroupEnd()

        self.AddStaticText(4110, c4d.BFH_LEFT, name="亮度")
        self.AddUserArea(UI_MANAGER_POWER_AREA,
                         c4d.BFH_SCALE | c4d.BFV_SCALE,
                         initw=390, inith=105)
        self.AttachUserArea(self.power_area, UI_MANAGER_POWER_AREA)
        self.GroupBegin(4102, c4d.BFH_SCALE, cols=2)
        self.AddButton(UI_MANAGER_POWER_DOWN, c4d.BFH_SCALE, name="降低 10%")
        self.AddButton(UI_MANAGER_POWER_UP, c4d.BFH_SCALE, name="提高 10%")
        self.GroupEnd()

        self.AddStaticText(4111, c4d.BFH_LEFT, name="颜色")
        self.AddColorField(UI_MANAGER_COLOR, c4d.BFH_SCALE,
                           initw=390, inith=34,
                           colorflags=self.COLOR_FLAGS)
        self.GroupBegin(4103, c4d.BFH_SCALE, cols=3)
        self.AddButton(UI_MANAGER_WHITE, c4d.BFH_SCALE, name="白色")
        self.AddButton(UI_MANAGER_WARM, c4d.BFH_SCALE, name="暖色")
        self.AddButton(UI_MANAGER_COOL, c4d.BFH_SCALE, name="冷色")
        self.GroupEnd()

        self.AddButton(UI_MANAGER_CLOSE, c4d.BFH_RIGHT, name="关闭")
        return True

    def InitValues(self):
        self.RebuildLightList()
        self.SetTimer(250)
        return True

    def RebuildLightList(self):
        doc = c4d.documents.GetActiveDocument()
        active = doc.GetActiveObject() if doc else None
        self.lights = _get_lights(doc) if doc else []
        self.FreeChildren(UI_MANAGER_LIGHT)

        selected_id = 0
        for index, obj in enumerate(self.lights, start=1):
            self.AddChild(UI_MANAGER_LIGHT, index, obj.GetName())
            if obj == active:
                selected_id = index

        if self.lights:
            if selected_id == 0:
                selected_id = 1
            self.SetInt32(UI_MANAGER_LIGHT, selected_id)
        else:
            self.AddChild(UI_MANAGER_LIGHT, 0, "场景中没有 Octane 灯光")
            self.SetInt32(UI_MANAGER_LIGHT, 0)
        self.color_object = None
        self.RefreshControls(force_color=True)

    def CurrentObject(self):
        selected_id = self.GetInt32(UI_MANAGER_LIGHT) or 0
        index = selected_id - 1
        if 0 <= index < len(self.lights):
            return self.lights[index]
        return None

    def SelectCurrent(self):
        doc = c4d.documents.GetActiveDocument()
        obj = self.CurrentObject()
        if doc is None or obj is None:
            return
        doc.SetActiveObject(obj, c4d.SELECTION_NEW)
        c4d.EventAdd()

    def RefreshControls(self, force_color=False):
        obj = self.CurrentObject()
        target = _get_power_target(obj)
        if obj is None or target is None:
            self.power_area.SetDisplay("没有可调节的 Octane 灯光", None)
        else:
            self.power_area.SetDisplay(obj.GetName(), target[2])

        color_valid = obj is not None and _get_color_target(obj) is not None
        self.Enable(UI_MANAGER_COLOR, color_valid)
        if color_valid and (force_color or obj != self.color_object):
            self.SetColorField(UI_MANAGER_COLOR, obj[c4d.LIGHT_COLOR],
                               1.0, 1.0, self.COLOR_FLAGS)
        self.color_object = obj if color_valid else None

    def AdjustPower(self, direction, qualifier=0):
        doc = c4d.documents.GetActiveDocument()
        obj = self.CurrentObject()
        value = _change_power(doc, obj, direction, qualifier) if doc else None
        if value is not None and obj is not None:
            self.power_area.SetDisplay(obj.GetName(), value)

    def ApplyColor(self, color):
        doc = c4d.documents.GetActiveDocument()
        obj = self.CurrentObject()
        if doc is not None and _set_light_color(doc, obj, color):
            self.color_object = obj

    def ApplyPreset(self, color):
        self.SetColorField(UI_MANAGER_COLOR, color, 1.0, 1.0,
                           self.COLOR_FLAGS)
        self.ApplyColor(color)

    def Command(self, command_id, msg):
        if command_id == UI_MANAGER_LIGHT:
            self.SelectCurrent()
            self.RefreshControls(force_color=True)
            return True
        if command_id == UI_MANAGER_REFRESH:
            self.RebuildLightList()
            return True
        if command_id == UI_MANAGER_SELECT:
            self.SelectCurrent()
            return True
        if command_id == UI_MANAGER_SOLO:
            doc = c4d.documents.GetActiveDocument()
            if doc:
                _solo(doc, self.CurrentObject())
            return True
        if command_id == UI_MANAGER_DEFAULT:
            doc = c4d.documents.GetActiveDocument()
            if doc:
                _solo_all(doc)
            return True
        if command_id == UI_MANAGER_POWER_DOWN:
            self.AdjustPower(-1)
            return True
        if command_id == UI_MANAGER_POWER_UP:
            self.AdjustPower(1)
            return True
        if command_id == UI_MANAGER_COLOR:
            data = self.GetColorField(UI_MANAGER_COLOR)
            if data:
                color = data.get("color", c4d.Vector(1.0, 1.0, 1.0))
                brightness = float(data.get("brightness", 1.0))
                self.ApplyColor(color * brightness)
            return True

        presets = {
            UI_MANAGER_WHITE: c4d.Vector(1.0, 1.0, 1.0),
            UI_MANAGER_WARM: c4d.Vector(1.0, 0.55, 0.25),
            UI_MANAGER_COOL: c4d.Vector(0.45, 0.68, 1.0),
        }
        if command_id in presets:
            self.ApplyPreset(presets[command_id])
            return True
        if command_id == UI_MANAGER_CLOSE:
            self.Close()
            return True
        return True

    def Timer(self, msg):
        doc = c4d.documents.GetActiveDocument()
        active = doc.GetActiveObject() if doc else None
        if active in self.lights:
            active_id = self.lights.index(active) + 1
            if self.GetInt32(UI_MANAGER_LIGHT) != active_id:
                self.SetInt32(UI_MANAGER_LIGHT, active_id)
                self.color_object = None
        self.RefreshControls()

    def AskClose(self):
        self.SetTimer(0)
        return False


class LightNameArea(gui.GeUserArea):
    def __init__(self, dialog, obj):
        super().__init__()
        self.dialog = dialog
        self.obj = obj

    def GetMinSize(self):
        return 180, 20

    def _color(self, color_id):
        value = self.GetColorRGB(color_id)
        return c4d.Vector(value["r"], value["g"], value["b"]) / 255.0

    def _fitted_name(self, width):
        name = self.obj.GetName()
        if self.DrawGetTextWidth(name) <= width:
            return name
        suffix = "…"
        low, high = 0, len(name)
        while low < high:
            middle = (low + high + 1) // 2
            if self.DrawGetTextWidth(name[:middle] + suffix) <= width:
                low = middle
            else:
                high = middle - 1
        return name[:low] + suffix

    def DrawMsg(self, x1, y1, x2, y2, msg):
        selected = self.obj.GetBit(c4d.BIT_ACTIVE)
        background = self._color(c4d.COLOR_BG)
        foreground = self._color(c4d.COLOR_TEXT_SELECTED if selected
                                 else c4d.COLOR_TEXT)
        self.DrawSetPen(background)
        self.DrawRectangle(x1, y1, x2, y2)
        self.DrawSetFont(c4d.FONT_STANDARD)
        self.DrawSetTextCol(foreground, background)
        text = self._fitted_name(max(1, x2 - x1 - 4))
        text_y = y1 + max(0, ((y2 - y1 + 1) - self.DrawGetFontHeight()) // 2)
        self.DrawText(text, x1 + 2, text_y)

    def InputEvent(self, msg):
        if (msg.GetInt32(c4d.BFM_INPUT_DEVICE) == c4d.BFM_INPUT_MOUSE and
                msg.GetInt32(c4d.BFM_INPUT_CHANNEL) == c4d.BFM_INPUT_MOUSELEFT):
            doc = c4d.documents.GetActiveDocument()
            if doc is not None:
                qualifier = msg.GetInt32(c4d.BFM_INPUT_QUALIFIER)
                control_pressed = bool(qualifier & c4d.QUALIFIER_CTRL)
                is_double_click = msg.GetBool(c4d.BFM_INPUT_DOUBLECLICK)
                is_selected = self.obj.GetBit(c4d.BIT_ACTIVE)

                if is_double_click:
                    # The first click has already applied the selection. Do not
                    # toggle it off again when Ctrl is held for a double-click.
                    if not is_selected:
                        mode = (c4d.SELECTION_ADD if control_pressed
                                else c4d.SELECTION_NEW)
                        doc.SetActiveObject(self.obj, mode)
                elif control_pressed:
                    mode = (c4d.SELECTION_SUB if is_selected
                            else c4d.SELECTION_ADD)
                    doc.SetActiveObject(self.obj, mode)
                else:
                    doc.SetActiveObject(self.obj, c4d.SELECTION_NEW)
                c4d.EventAdd()
                self.dialog.RedrawNameAreas()
            if msg.GetBool(c4d.BFM_INPUT_DOUBLECLICK):
                self.dialog.pending_name_object = self.obj
            return True
        return False


class GroupedLightManagerDialog(gui.GeDialog):
    COLOR_FLAGS = (c4d.DR_COLORFIELD_ENABLE_COLORWHEEL |
                   c4d.DR_COLORFIELD_ENABLE_HSV |
                   c4d.DR_COLORFIELD_ENABLE_RGB |
                   c4d.DR_COLORFIELD_ENABLE_KELVIN |
                   c4d.DR_COLORFIELD_ENABLE_SWATCHES |
                   c4d.DR_COLORFIELD_ICC_BASEDOC)

    def __init__(self):
        super().__init__()
        self.lights = []
        self.control_map = {}
        self.row_records = []
        self.scene_signature = ()
        self.slider_maxima = {}
        self.editing_name_key = None
        self.editing_name_id = None
        self.editing_original_name = ""
        self.editing_had_focus = False
        self.pending_name_object = None
        self.name_areas = []
        self.solo_buttons = {}
        self.camera_buttons = {}
        self.last_selected_keys = ()

    def CreateLayout(self):
        self.SetTitle("Octane 灯光管理器")
        self.GroupBegin(4300, c4d.BFH_SCALEFIT, cols=4)
        self.AddStaticText(4301, c4d.BFH_LEFT | c4d.BFH_SCALE,
                           name="灯光列表")
        self.AddButton(UI_GROUP_SOLO_SELECTED, c4d.BFH_FIT,
                       name="独显所选")
        self.AddButton(UI_GROUP_DEFAULT_ALL, c4d.BFH_FIT,
                       name="全部默认")
        self.AddButton(UI_GROUP_REFRESH, c4d.BFH_FIT,
                       name="刷新")
        self.GroupEnd()

        self.ScrollGroupBegin(UI_GROUP_SCROLL,
                              c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                              c4d.SCROLLGROUP_VERT |
                              c4d.SCROLLGROUP_AUTOVERT |
                              c4d.SCROLLGROUP_BORDERIN,
                              initw=720, inith=330)
        self.GroupBegin(UI_GROUP_ROWS,
                        c4d.BFH_SCALEFIT | c4d.BFV_TOP,
                        cols=1)
        self.GroupEnd()
        self.GroupEnd()

        self.AddStaticText(UI_GROUP_STATUS, c4d.BFH_SCALE,
                           name="正在扫描 Octane 灯光…")
        return True

    def InitValues(self):
        self.BuildRows()
        self.SetTimer(300)
        return True

    def _signature(self, lights):
        return tuple((obj.GetName(), obj.GetType(), _is_environment_light(obj))
                     for obj in lights)

    def _add_column_header(self, group_id):
        self.GroupBegin(group_id, c4d.BFH_SCALEFIT, cols=7)
        self.AddStaticText(group_id + 1, c4d.BFH_CENTER,
                           initw=22, name="显")
        self.AddStaticText(group_id + 2, c4d.BFH_LEFT,
                           initw=180, name="灯光")
        self.AddStaticText(group_id + 3, c4d.BFH_CENTER,
                           initw=28, name="")
        self.AddStaticText(group_id + 4, c4d.BFH_CENTER,
                           initw=28, name="")
        self.AddStaticText(group_id + 5, c4d.BFH_SCALEFIT,
                           initw=300, name="功率")
        self.AddStaticText(group_id + 6, c4d.BFH_CENTER,
                           initw=72, name="数值")
        self.AddStaticText(group_id + 7, c4d.BFH_CENTER,
                           initw=52, name="颜色")
        self.GroupEnd()

    def _add_icon_button(self, control_id, icon_id, tooltip, toggle=False):
        settings = c4d.BaseContainer()
        settings.SetBool(c4d.BITMAPBUTTON_BUTTON, True)
        settings.SetBool(c4d.BITMAPBUTTON_TOGGLE, toggle)
        settings.SetInt32(c4d.BITMAPBUTTON_ICONID1, icon_id)
        settings.SetInt32(c4d.BITMAPBUTTON_ICONID2, icon_id)
        settings.SetInt32(c4d.BITMAPBUTTON_FORCE_SIZE, 18)
        settings.SetString(c4d.BITMAPBUTTON_TOOLTIP, tooltip)
        button = self.AddCustomGui(control_id, c4d.CUSTOMGUI_BITMAPBUTTON, "",
                                   c4d.BFH_CENTER, 28, 20, settings)

        # Use Cinema 4D's own disabled icon rendering for the off state. The
        # gadget itself remains enabled, so a grey icon can still be clicked.
        source = gui.GetIcon(icon_id)
        if source and button is not None:
            def make_icon(disabled):
                icon = c4d.IconData()
                if isinstance(source, dict):
                    icon.bmp = source.get("bmp")
                    icon.x = source.get("x", 0)
                    icon.y = source.get("y", 0)
                    icon.w = source.get("w", 0)
                    icon.h = source.get("h", 0)
                else:
                    icon.bmp = source.bmp
                    icon.x = source.x
                    icon.y = source.y
                    icon.w = source.w
                    icon.h = source.h
                icon.flags = (c4d.ICONDATAFLAGS_DISABLED if disabled
                              else c4d.ICONDATAFLAGS_NONE)
                return icon

            button.SetImage(make_icon(False), True, False)
            button.SetImage(make_icon(True), True, True)
        return button

    def _add_light_row(self, obj, index):
        base = ROW_CONTROL_BASE + index * ROW_CONTROL_STRIDE
        visible_id = base
        name_id = base + 1
        solo_id = base + 2
        slider_id = base + 3
        value_id = base + 4
        color_id = base + 5
        camera_id = base + 6

        self.GroupBegin(20000 + index, c4d.BFH_SCALEFIT, cols=7)
        self.AddCheckbox(visible_id, c4d.BFH_CENTER, 22, 0, "")
        if self.editing_name_key == self._object_key(obj):
            self.AddEditText(name_id, c4d.BFH_LEFT,
                             initw=180,
                             editflags=c4d.EDITTEXT_NOENTERKEYFORWARDING)
            self.editing_name_id = name_id
        else:
            name_area = LightNameArea(self, obj)
            self.AddUserArea(name_id, c4d.BFH_LEFT,
                             initw=180, inith=20)
            self.AttachUserArea(
                name_area, name_id,
                c4d.USERAREAFLAGS_COREMESSAGE |
                c4d.USERAREAFLAGS_NOHANDLEFOCUS)
            self.name_areas.append(name_area)
        solo_button = self._add_icon_button(
            solo_id, ICON_SOLO, "独显此灯光", toggle=True)
        self.solo_buttons[self._object_key(obj)] = solo_button
        camera_button = self._add_icon_button(
            camera_id, ICON_CAMERA_VISIBILITY, "摄像机可见", toggle=True)
        self.camera_buttons[camera_id] = camera_button
        self.AddSlider(slider_id, c4d.BFH_SCALEFIT,
                       initw=300)
        self.AddEditNumber(value_id, c4d.BFH_RIGHT,
                           initw=72)
        self.AddColorField(color_id, c4d.BFH_CENTER,
                           initw=52, inith=0,
                           colorflags=self.COLOR_FLAGS)
        self.GroupEnd()

        self.control_map[visible_id] = ("visible", obj)
        self.control_map[name_id] = ("name", obj)
        self.control_map[solo_id] = ("solo", obj)
        self.control_map[camera_id] = ("camera_visibility", obj)
        self.control_map[slider_id] = ("power_slider", obj)
        self.control_map[value_id] = ("power_value", obj)
        self.control_map[color_id] = ("color", obj)
        self.row_records.append((obj, visible_id, name_id, camera_id,
                                 slider_id, value_id, color_id))

    def _add_category(self, title, lights, group_offset, start_index):
        self.AddStaticText(30000 + group_offset, c4d.BFH_LEFT,
                           name=f"▼ {title}（{len(lights)}）")
        self._add_column_header(31000 + group_offset)
        for offset, obj in enumerate(lights):
            self._add_light_row(obj, start_index + offset)

    def BuildRows(self):
        doc = c4d.documents.GetActiveDocument()
        self.lights = _get_lights(doc) if doc else []
        regular = [obj for obj in self.lights if not _is_environment_light(obj)]
        environment = [obj for obj in self.lights if _is_environment_light(obj)]

        self.control_map = {}
        self.row_records = []
        self.name_areas = []
        self.solo_buttons = {}
        self.camera_buttons = {}
        self.editing_name_id = None
        self.LayoutFlushGroup(UI_GROUP_ROWS)
        if regular:
            self._add_category("常规灯光", regular, 0, 0)
        if environment:
            self._add_category("环境灯光", environment, 100, len(regular))
        if not self.lights:
            self.AddStaticText(39999, c4d.BFH_CENTER,
                               name="场景中没有识别到 Octane 灯光")
        self.LayoutChanged(UI_GROUP_ROWS)
        if self.editing_name_id is not None:
            self.SetString(self.editing_name_id, self.editing_original_name)
            self.Activate(self.editing_name_id)
        self.scene_signature = self._signature(self.lights)
        self.RefreshRows()

    def _object_key(self, obj):
        try:
            return int(obj.GetGUID())
        except Exception:
            return id(obj)

    def _slider_settings(self, obj, target):
        _tag, _parameter_id, value, maximum = target
        key = self._object_key(obj)
        slider_max = self.slider_maxima.get(key, 100.0)
        slider_max = min(max(100.0, slider_max, value), maximum)
        self.slider_maxima[key] = slider_max
        return value, slider_max, maximum

    def _set_slider_value(self, slider_id, value, slider_max):
        self.SetFloat(slider_id, value,
                      min=0.0001, max=slider_max, step=0.01,
                      format=c4d.FORMAT_FLOAT,
                      min2=0.0001, max2=slider_max,
                      quadscale=False)

    def _set_number_value(self, value_id, value, maximum):
        self.SetFloat(value_id, value,
                      min=0.0001, max=maximum, step=0.01,
                      format=c4d.FORMAT_FLOAT,
                      min2=0.0001, max2=maximum,
                      quadscale=False)

    def RefreshRows(self):
        for obj, visible_id, _name_id, camera_id, slider_id, value_id, color_id in self.row_records:
            try:
                visibility = _get_render_visibility(obj)
                if not self.IsActive(visible_id):
                    self.SetBool(visible_id, visibility != c4d.MODE_OFF)

                solo_button = self.solo_buttons.get(self._object_key(obj))
                if solo_button is not None:
                    # BitmapButton's second image is displayed for True.
                    # The second image is our grey/inactive variant.
                    solo_button.SetToggleState(visibility == c4d.MODE_OFF)

                camera_target = _get_camera_visibility_target(obj)
                camera_button = self.camera_buttons.get(camera_id)
                self.Enable(camera_id, camera_target is not None)
                if camera_target is not None and camera_button is not None:
                    camera_button.SetToggleState(not bool(camera_target[2]))

                target = _get_power_target(obj)
                if target is not None:
                    value, slider_max, maximum = self._slider_settings(obj, target)
                    if not self.IsActive(slider_id):
                        self._set_slider_value(slider_id, value, slider_max)
                    if not self.IsActive(value_id):
                        self._set_number_value(value_id, value, maximum)

                color_valid = _get_color_target(obj) is not None
                self.Enable(color_id, color_valid)
                if color_valid and not self.IsActive(color_id):
                    self.SetColorField(color_id, obj[c4d.LIGHT_COLOR],
                                       1.0, 1.0, self.COLOR_FLAGS)
            except Exception:
                continue

        self.SetString(UI_GROUP_STATUS,
                       f"共 {len(self.lights)} 盏灯光 · 滑条支持拖动/滚轮 · 颜色块点击打开吸管")

    def _begin_name_edit(self, obj):
        self.editing_name_key = self._object_key(obj)
        self.editing_original_name = obj.GetName()
        self.editing_had_focus = False
        self.BuildRows()

    def RedrawNameAreas(self):
        for area in self.name_areas:
            area.Redraw()

    def _finish_name_edit(self, cancel=False):
        if self.editing_name_key is None:
            return

        obj = None
        for row_obj, _visible_id, _name_id, _camera_id, _slider_id, _value_id, _color_id in self.row_records:
            if self._object_key(row_obj) == self.editing_name_key:
                obj = row_obj
                break

        new_name = self.editing_original_name
        if not cancel and self.editing_name_id is not None:
            entered = (self.GetString(self.editing_name_id) or "").strip()
            if entered:
                new_name = entered

        old_name = self.editing_original_name
        self.editing_name_key = None
        self.editing_name_id = None
        self.editing_original_name = ""
        self.editing_had_focus = False

        doc = c4d.documents.GetActiveDocument()
        if obj is not None and doc is not None and new_name != old_name:
            doc.StartUndo()
            doc.AddUndo(c4d.UNDOTYPE_CHANGE, obj)
            obj.SetName(new_name)
            doc.EndUndo()
            c4d.EventAdd()
        self.BuildRows()

    def Message(self, msg, result):
        if msg.GetId() == c4d.BFM_INPUT:
            device = msg.GetInt32(c4d.BFM_INPUT_DEVICE)
            channel = msg.GetInt32(c4d.BFM_INPUT_CHANNEL)

            if (device == c4d.BFM_INPUT_KEYBOARD and
                    self.editing_name_id is not None):
                if channel == c4d.KEY_ENTER:
                    self._finish_name_edit(False)
                    return True
                if channel == c4d.KEY_ESC:
                    self._finish_name_edit(True)
                    return True

        return gui.GeDialog.Message(self, msg, result)

    def _handle_row_command(self, command_id):
        action, obj = self.control_map[command_id]
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return True

        if action == "visible":
            value = c4d.MODE_UNDEF if self.GetBool(command_id) else c4d.MODE_OFF
            doc.StartUndo()
            doc.AddUndo(c4d.UNDOTYPE_CHANGE, obj)
            _set_render_visibility(obj, value)
            doc.EndUndo()
            c4d.EventAdd()
        elif action == "solo":
            doc.SetActiveObject(obj, c4d.SELECTION_NEW)
            _solo(doc, obj)
        elif action == "camera_visibility":
            target = _get_camera_visibility_target(obj)
            if target is not None:
                _set_camera_visibility(doc, obj, not bool(target[2]),
                                       target=target)
            self.RefreshRows()
        elif action == "name":
            return True
        elif action == "power_slider":
            value = self.GetFloat(command_id)
            _set_power_value(doc, obj, value)
            for row_obj, _visible_id, _name_id, _camera_id, slider_id, value_id, _color_id in self.row_records:
                if row_obj == obj:
                    target = _get_power_target(obj)
                    if target is not None:
                        self._set_number_value(value_id, value, target[3])
                    break
        elif action == "power_value":
            value = self.GetFloat(command_id)
            target = _get_power_target(obj)
            if target is not None:
                key = self._object_key(obj)
                self.slider_maxima[key] = min(max(100.0, value), target[3])
                slider_max = self.slider_maxima[key]
                for row_obj, _visible_id, _name_id, _camera_id, slider_id, _value_id, _color_id in self.row_records:
                    if row_obj == obj:
                        self._set_slider_value(slider_id, value, slider_max)
                        break
            _set_power_value(doc, obj, value)
        elif action == "color":
            data = self.GetColorField(command_id)
            if data:
                color = data.get("color", c4d.Vector(1.0, 1.0, 1.0))
                brightness = float(data.get("brightness", 1.0))
                _set_light_color(doc, obj, color * brightness)
        return True

    def Command(self, command_id, msg):
        if command_id == UI_GROUP_SOLO_SELECTED:
            doc = c4d.documents.GetActiveDocument()
            if doc:
                _solo(doc, doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_0))
            self.RefreshRows()
            return True
        if command_id == UI_GROUP_DEFAULT_ALL:
            doc = c4d.documents.GetActiveDocument()
            if doc:
                _solo_all(doc)
            self.RefreshRows()
            return True
        if command_id == UI_GROUP_REFRESH:
            self.BuildRows()
            return True
        if command_id in self.control_map:
            return self._handle_row_command(command_id)
        return True

    def Timer(self, msg):
        if self.pending_name_object is not None:
            obj = self.pending_name_object
            self.pending_name_object = None
            self._begin_name_edit(obj)
            return

        doc = c4d.documents.GetActiveDocument()
        selected_objects = (doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_0)
                            if doc else [])
        selected_keys = tuple(sorted(self._object_key(obj)
                                     for obj in selected_objects))
        if selected_keys != self.last_selected_keys:
            self.last_selected_keys = selected_keys
            self.RedrawNameAreas()
        current = _get_lights(doc) if doc else []
        controls_active = any(self.IsActive(record[4]) or self.IsActive(record[5])
                              for record in self.row_records)
        if self.editing_name_id is not None:
            if self.IsActive(self.editing_name_id):
                self.editing_had_focus = True
            elif self.editing_had_focus:
                self._finish_name_edit(False)
                return
            controls_active = True
        if self._signature(current) != self.scene_signature and not controls_active:
            self.BuildRows()
        else:
            self.RefreshRows()

    def AskClose(self):
        self.SetTimer(0)
        return False


_manager_dialog = GroupedLightManagerDialog()


class ManagerCommand(plugins.CommandData):
    def Execute(self, doc):
        opened = _manager_dialog.Open(c4d.DLG_TYPE_ASYNC,
                                      pluginid=CMD_MANAGER,
                                      xpos=-1, ypos=-1,
                                      defaultw=760, defaulth=390)
        if opened:
            _manager_dialog.BuildRows()
        return opened

    def RestoreLayout(self, secret):
        return _manager_dialog.Restore(CMD_MANAGER, secret)


def _build_direct_menu_item():
    item = c4d.BaseContainer()
    item.InsData(c4d.MENURESOURCE_SUBTITLE, "OC灯光工具")
    item.InsData(c4d.MENURESOURCE_COMMAND,
                 f"PLUGIN_CMD_{CMD_MANAGER}")
    return item


def PluginMessage(msg_id, data):
    if msg_id == c4d.C4DPL_BUILDMENU:
        main_menu = gui.GetMenuResource("M_EDITOR")
        if main_menu:
            main_menu.InsData(c4d.MENURESOURCE_STRING,
                              _build_direct_menu_item())
    return True


# Use positional arguments for the C4D 2026.2 Python binding. In this build,
# the required icon slot is not reliably satisfied by a keyword argument.
plugins.RegisterCommandPlugin(CMD_SOLO_SELECTED,
                              "Octane灯光独显：选中灯光", 0, None,
                              "只保留当前选中的 Octane 灯光参与渲染",
                              SoloSelectedCommand())
plugins.RegisterCommandPlugin(CMD_SOLO_ALL,
                              "Octane灯光独显：全部恢复默认", 0, None,
                              "将全部 Octane 灯光恢复为渲染可见性默认状态",
                              SoloAllCommand())
plugins.RegisterCommandPlugin(CMD_BRIGHTNESS,
                              "Octane灯光独显：亮度滚轮调节", 0, None,
                              "使用鼠标滚轮快捷调节选中 Octane 灯光的功率",
                              BrightnessCommand())
plugins.RegisterCommandPlugin(CMD_COLOR,
                              "Octane灯光独显：颜色快捷调节", 0, None,
                              "使用原生颜色选择器和预设调节 Octane 灯光颜色",
                              ColorCommand())
plugins.RegisterCommandPlugin(CMD_MANAGER,
                              "OC灯光工具", 0, None,
                              "在一个面板中管理全部 Octane 灯光",
                              ManagerCommand())

