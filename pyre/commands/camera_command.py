import nornir_imageregistration.spatial

try:
    import PyQt6.Key  # type: ignore[import-untyped]
    import PyQt6.QtCore
    from PyQt6.QtCore import Qt
except:
    print("Import failure during documentation generation (expected)")

import pyre.commands.uicommandbase as uicommand_base


class CameraCommand(uicommand_base.UICommandBase):
    '''
    The user interface to adjust the camera
    '''

    def __init__(self, parent, completed_func, camera):
        super(CameraCommand, self).__init__(parent, completed_func)
        self.LastMousePosition = None

    def on_key_press(self, e):
        keycode = e.GetKeyCode()

        symbol = ''
        try:
            KeyChar = '%c' % keycode
            symbol = KeyChar.lower()
        except:
            pass

        if symbol == 'a':  # "A" Character
            ImageDX = 0.1 * self.camera.visible_world_width  # type: ignore[attr-defined]
            self.camera.x = self.camera.x + ImageDX  # type: ignore[attr-defined]
        elif symbol == 'd':  # "D" Character
            ImageDX = -0.1 * self.camera.visible_world_width  # type: ignore[attr-defined]
            self.camera.x = self.camera.x + ImageDX  # type: ignore[attr-defined]
        elif symbol == 'w':  # "W" Character
            ImageDY = -0.1 * self.camera.visible_world_height  # type: ignore[attr-defined]
            self.camera.y = self.camera.y + ImageDY  # type: ignore[attr-defined]
        elif symbol == 's':  # "S" Character
            ImageDY = 0.1 * self.camera.visible_world_height  # type: ignore[attr-defined]
            self.camera.y = self.camera.y + ImageDY  # type: ignore[attr-defined]
        elif keycode == Qt.Key.Key_PageUp:
            self.camera.scale = self.scale * 0.9  # type: ignore[attr-defined]
        elif keycode == Qt.Key.Key_PageDown:
            self.camera.scale *= 1.1  # type: ignore[attr-defined]
        elif symbol == 'm':
            LookAt = [self.camera.x, self.camera.y]  # type: ignore[attr-defined]

            if not self.FixedSpace and self.ShowWarped:  # type: ignore[attr-defined]
                LookAt = self.TransformController.transform([LookAt])  # type: ignore[attr-defined]
                LookAt = LookAt[0]

    def on_mouse_scroll(self, e):

        if self.camera is None:  # type: ignore[attr-defined]
            return

        scroll_y = e.GetWheelRotation() / 120.0

        # We rotate when command is down
        if not e.CmdDown():
            zdelta = (1 + (-scroll_y / 20))

            new_scale = self.camera.scale * zdelta  # type: ignore[attr-defined]
            max_image_dimension_value = max([self.TransformController.width, self.TransformController.height])  # type: ignore[attr-defined]
            if new_scale > max_image_dimension_value * 2.0:
                new_scale = max_image_dimension_value * 2.0

            if new_scale < 0.5:
                new_scale = 0.5

            self.camera.scale = new_scale  # type: ignore[attr-defined]

            self.statusBar.update_status_bar(self.LastMousePosition)  # type: ignore[attr-defined]

    def on_mouse_drag(self, e):
        try:
            (y, x) = self.GetCorrectedMousePosition(e)  # type: ignore[attr-defined]

            if self.LastMousePosition is None:
                self.LastMousePosition = (y, x)
                return

            dx = x - self.LastMousePosition[nornir_imageregistration.iPoint.X]
            dy = (y - self.LastMousePosition[nornir_imageregistration.iPoint.Y])

            self.LastMousePosition = (y, x)

            ImageY, ImageX = self.camera.ImageCoordsForMouse(y, x)  # type: ignore[attr-defined]
            if ImageX is None:
                return

            ImageDX = (float(dx) / self.width) * self.camera.visible_world_width  # type: ignore[attr-defined]
            ImageDY = (float(dy) / self.height) * self.camera.visible_world_height  # type: ignore[attr-defined]

            if e.RightIsDown():
                self.camera.lookat((self.camera.y - ImageDY, self.camera.x - ImageDX))  # type: ignore[attr-defined]
                self.statusBar.update_status_bar(self.LastMousePosition)  # type: ignore[attr-defined]
        finally:
            # We always skip the event in case others care about mouse motion
            e.Skip()
