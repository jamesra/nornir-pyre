import nornir_imageregistration.spatial

try:
    import wx
except:
    print("Ignoring wx import failure, assumed documentation use, otherwise please install wxPython")

import pyre.commands.commandbase as command_base


class CameraCommand(command_base.CommandBase):
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
            ImageDX = 0.1 * self.camera.visible_world_width
            self.camera.x = self.camera.x + ImageDX
        elif symbol == 'd':  # "D" Character
            ImageDX = -0.1 * self.camera.visible_world_width
            self.camera.x = self.camera.x + ImageDX
        elif symbol == 'w':  # "W" Character
            ImageDY = -0.1 * self.camera.visible_world_height
            self.camera.y = self.camera.y + ImageDY
        elif symbol == 's':  # "S" Character
            ImageDY = 0.1 * self.camera.visible_world_height
            self.camera.y = self.camera.y + ImageDY
        elif keycode == wx.WXK_PAGEUP:
            self.camera.scale = self.scale * 0.9
        elif keycode == wx.WXK_PAGEDOWN:
            self.camera.scale *= 1.1
        elif symbol == 'm':
            LookAt = [self.camera.x, self.camera.y]

            if not self.FixedSpace and self.ShowWarped:
                LookAt = self.TransformController.transform([LookAt])
                LookAt = LookAt[0]

    def on_mouse_scroll(self, e):

        if self.camera is None:
            return

        scroll_y = e.GetWheelRotation() / 120.0

        # We rotate when command is down
        if not e.CmdDown():
            zdelta = (1 + (-scroll_y / 20))

            new_scale = self.camera.scale * zdelta
            max_image_dimension_value = max([self.TransformController.width, self.TransformController.height])
            if new_scale > max_image_dimension_value * 2.0:
                new_scale = max_image_dimension_value * 2.0

            if new_scale < 0.5:
                new_scale = 0.5

            self.camera.scale = new_scale

            self.statusBar.update_status_bar(self.LastMousePosition)

    def on_mouse_drag(self, e):
        try:
            (y, x) = self.GetCorrectedMousePosition(e)

            if self.LastMousePosition is None:
                self.LastMousePosition = (y, x)
                return

            dx = x - self.LastMousePosition[nornir_imageregistration.iPoint.X]
            dy = (y - self.LastMousePosition[nornir_imageregistration.iPoint.Y])

            self.LastMousePosition = (y, x)

            ImageY, ImageX = self.camera.ImageCoordsForMouse(y, x)
            if ImageX is None:
                return

            ImageDX = (float(dx) / self.width) * self.camera.visible_world_width
            ImageDY = (float(dy) / self.height) * self.camera.visible_world_height

            if e.RightIsDown():
                self.camera.lookat((self.camera.y - ImageDY, self.camera.x - ImageDX))
                self.statusBar.update_status_bar(self.LastMousePosition)
        finally:
            # We always skip the event in case others care about mouse motion
            e.Skip()
