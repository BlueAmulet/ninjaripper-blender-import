bl_info = {
   "name": "NinjaRipper RIP Format",
   "author": "kree-nickm",
   "version": (0, 1, 0),
   "blender": (2, 80, 0),
   "location": "File > Import",
   "description": "Import files created by NinjaRipper",
   "category": "Import"}

import bpy
import os
import traceback
from bpy.props import BoolProperty, FloatProperty, StringProperty, EnumProperty
from bpy_extras.io_utils import ImportHelper
from .RipFile import RipFile
from .RipMesh import RipMesh

class ImportRIP(bpy.types.Operator, ImportHelper):
   bl_idname = "import_scene.rip"
   bl_label = 'Import NinjaRipper (*.rip)'
   bl_options = {'UNDO'}
   filename_ext = ".rip"

   filter_glob: StringProperty(default="*.rip", options={'HIDDEN'}, maxlen=255)
   xyzOrder: bpy.props.EnumProperty(items=(('Xzy', '-X, Z, Y', '-X, Z, Y'),
                                           ('xyz', 'X, Y, Z',  'X, Y, Z')), name="Vertex Order")
   uvOrder: bpy.props.EnumProperty(items=(('uW', 'U, -V+1', 'U, -V+1'),
                                          ('uv', 'U, V',    'U, V')), name="UV Order")
   scale: FloatProperty(name="Scale", default=1.0)
   reuseMats: BoolProperty(name="Re-use materials", description="Re-use existing materials from other RIP files", default=True)
   packTextures: BoolProperty(name="Pack textures", description="Pack textures into the .blend for non conflicting filenames", default=True)
   importAll: BoolProperty(name="Import entire folder", description="Import all meshes in this folder", default=False)
   importShaders: BoolProperty(name="Import shaders", description="Import shader files into materials (SEE INSTRUCTIONS BEFORE YOU DO THIS)", default=False)
   keep2D: BoolProperty(name="Keep 2D meshes", description="Keep meshes that are not three-dimensional", default=False)
   keepUntextured: BoolProperty(name="Keep untextured meshes", description="Keep meshes that have no textures associated with them", default=False)
   removeDuplicates: BoolProperty(name="Remove duplicate meshes", description="EXPERIMENTAL. Attempts to remove meshes that *seem* to be the same, keeping the one with more textures", default=False)
   deleteDuplicates: BoolProperty(name="Delete duplicate meshes", description="Delete .rip files removed by the 'Remove duplicate meshes' option", default=False)

   def draw(self, context):
      layout = self.layout
      sub = layout.row()
      sub.prop(self, "xyzOrder")
      sub = layout.row()
      sub.prop(self, "uvOrder")
      sub = layout.row()
      sub.prop(self, "scale")
      sub = layout.row()
      sub.prop(self, "reuseMats")
      sub = layout.row()
      sub.prop(self, "packTextures")
      sub = layout.row()
      sub.prop(self, "importAll")
      sub = layout.row()
      sub.prop(self, "importShaders")
      sub = layout.row()
      sub.prop(self, "keep2D")
      sub = layout.row()
      sub.prop(self, "keepUntextured")
      sub = layout.row()
      sub.prop(self, "removeDuplicates")
      sub = layout.row()
      sub.prop(self, "deleteDuplicates")

   def execute(self, context):
      wm = bpy.context.window_manager
      if self.importAll:
         ripFiles = []
         walkDir = self.filepath
         if os.path.isfile(walkDir):
            walkDir = os.path.dirname(walkDir)
         for root, dirs, files in os.walk(walkDir):
            for file in files:
               if file.lower().endswith(".rip"):
                  ripFiles.append(RipFile(os.path.join(root, file)))
      else:
         ripFiles = [RipFile(self.filepath)]

      wm.progress_begin(0, len(ripFiles))
      for i, rip in enumerate(ripFiles):
         wm.progress_update(i)
         rip.parse(xyzOrder=self.xyzOrder, uvOrder=self.uvOrder, scale=self.scale, keep2D=self.keep2D, keepUntextured=self.keepUntextured)
      wm.progress_end()
      numBefore = len(ripFiles)
      ripFiles = list(filter(lambda r: r.parsed, ripFiles))
      print("Total RIP files skipped: {}".format(numBefore - len(ripFiles)))

      if self.removeDuplicates:
         ripFilesFinal = []
         wm.progress_begin(0, len(ripFiles))
         for i, rip in enumerate(ripFiles):
            wm.progress_update(i)
            add = True
            for r in range(len(ripFilesFinal)):
               if rip.seemsEqual(ripFilesFinal[r]):
                  # TODO: If some of the first rips we find duplicates for have equal texture counts, the duplicates will be kept. If later, a duplicate rip with more textures comes along, only the first duplicate rip will be overwritten, and the other duplicate(s) will still remain.
                  add = False
                  if len(rip.textures) > len(ripFilesFinal[r].textures):
                     ripFilesFinal[r] = rip
                  elif self.deleteDuplicates:
                     os.remove(rip.filePath)
                  break
            if add:
               ripFilesFinal.append(rip)
         wm.progress_end()
         print("Total duplicate meshes skipped: {}".format(len(ripFiles) - len(ripFilesFinal)))
      else:
         ripFilesFinal = ripFiles

      wm.progress_begin(0, len(ripFilesFinal))
      failedLoad = 0
      for i, rip in enumerate(ripFilesFinal):
         wm.progress_update(i)
         mesh = RipMesh(rip)
         mesh.loadMaterial(self.reuseMats, self.packTextures, self.importShaders)
         try:
            mesh.loadRip()
         except Exception as e:
            print(f"Exception occured loading {rip}:")
            traceback.print_exc()
            failedLoad += 1
            bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
      wm.progress_end()
      if failedLoad > 0:
         message = f"{failedLoad} meshes failed to load"
         print(message)
         self.report({'ERROR'}, message)
      return {'FINISHED'}

def menu_func_import(self, context):
   self.layout.operator(ImportRIP.bl_idname, text="NinjaRipper (.rip)")

def register():
   from bpy.utils import register_class
   register_class(ImportRIP)
   bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
   from bpy.utils import unregister_class
   unregister_class(ImportRIP)
   bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
   register()
