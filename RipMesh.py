import bpy
import mathutils
import hashlib
import time
import zlib
import os
import shutil
from math import floor

class RipMesh:
   def __init__(self, ripFile):
      self.ripFile = ripFile
      self.mesh = bpy.data.meshes.new(self.ripFile.fileLabel + "Mesh")
      self.object = bpy.data.objects.new(self.ripFile.fileLabel, self.mesh)

   def loadRip(self):
      loadStart = time.process_time()
      bpy.context.collection.objects.link(self.object)
      bpy.context.view_layer.objects.active = self.object
      bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
      positions = None
      normals = None
      uvs = []
      for sem in self.ripFile.semantics:
         if sem['nameUpper'] == "POSITION" and positions is None:
            positions = sem
         if sem['nameUpper'] == "NORMAL" and normals is None:
            normals = sem
         if sem['nameUpper'] == "TEXCOORD":
            uvs.append(sem)

      vertMap = {}
      vertSet = {}
      bpyVertices = []
      bpyNormals = []
      for i, vert in enumerate(self.ripFile.vertexes):
         vert_key = tuple(sorted([(k, tuple(vert[k])) for k in vert if k != "index" and not k.startswith("TEXCOORD")]))
         if vert_key in vertSet:
            vertMap[i] = vertSet[vert_key]
         else:
            vertMap[i] = len(vertSet)
            vertSet[vert_key] = len(vertSet)
            bpyVertices.append(vert[positions['label']])
            if normals:
                bpyNormals.append(vert[normals['label']][0:3]) # I've seen rips with 4-dimensional normals, no idea what the deal is with that

      bpyFaces = []
      for f in self.ripFile.faces:
         bpyFaces.append((vertMap[f[0]], vertMap[f[1]], vertMap[f[2]]))

      self.mesh.from_pydata(bpyVertices, [], bpyFaces)
      self.mesh.polygons.foreach_set('use_smooth', (True,)*len(bpyFaces))

      for i, uv in enumerate(uvs):
         uvs[i] = (uv, self.mesh.uv_layers.new(name='UVMap' + ('' if i == 0 else str(i + 1))))
      for i, face in enumerate(self.mesh.polygons):
         ripFace = self.ripFile.faces[i]
         for uv in uvs:
            for uv_set_loop in range(3):
               uv[1].data[face.loop_indices[uv_set_loop]].uv = self.ripFile.vertexes[ripFace[uv_set_loop]][uv[0]['label']]

      if len(bpyNormals) > 0:
         self.mesh.normals_split_custom_set_from_vertices(bpyNormals)
      self.mesh.use_auto_smooth = True
      # Toggling seems to fix weird mesh appearance in some cases.
      bpy.ops.object.mode_set(mode='EDIT', toggle=False)
      bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
      loadTime = time.process_time() - loadStart
      print("{}: RIP load took {}s".format(self.ripFile.fileLabel, loadTime))
      return self.mesh

   def loadMaterial(self, reuseMats=True, packTextures=True, importShaders=False):
      self.material = None
      if len(self.ripFile.textures) > 0:
         texHashes = []
         for t in self.ripFile.textures:
            with open(t['filePath'], 'rb') as f:
               texHashes.append(hashlib.md5(f.read()).hexdigest())
         texHashes.sort()
         materialName = hashlib.md5(','.join(texHashes).encode('utf-8')).hexdigest()
      else:
         materialName = None

      if materialName is not None and materialName in bpy.data.materials and reuseMats:
         self.material = bpy.data.materials[materialName]
      elif materialName is not None:
         self.material = bpy.data.materials.new(name=materialName)
         self.material.use_nodes = True
         if importShaders:
            for shader in self.ripFile.shaders:
               if shader.shaderType == 1:
                  self.loadShader(shader)
         else:
            bsdf = self.material.node_tree.nodes["Principled BSDF"]
            bsdf.inputs["Roughness"].default_value = 1
            bsdf.inputs["Specular"].default_value = 0
            for t in range(len(self.ripFile.textures)):
               tex = self.material.node_tree.nodes.new('ShaderNodeTexImage')
               with open(self.ripFile.textures[t]['filePath'], 'rb') as f:
                  texHash = hex(zlib.crc32(f.read()))[2:].zfill(8).upper() + os.path.splitext(self.ripFile.textures[t]['fileName'])[1]
               if texHash in bpy.data.images:
                  tex.image = bpy.data.images[texHash]
               else:
                  #copyName = "Z:\\textures\\" + texHash
                  #shutil.copy2(self.ripFile.textures[t]['filePath'], copyName)
                  copyName = self.ripFile.textures[t]['filePath']
                  tex.image = bpy.data.images.load(copyName, check_existing=True)
                  tex.image.name = texHash
                  if packTextures:
                     tex.image.reload()
                     tex.image.pack()
                     tex.image.filepath_raw = texHash
               tex.hide = True
               tex.location = [-300, -50*t]
               if self.ripFile.textures[t]['filePath'].lower().endswith('_1.dds'):
                  self.material.node_tree.links.new(bsdf.inputs['Base Color'], tex.outputs['Color'])
                  self.material.node_tree.links.new(bsdf.inputs['Alpha'],      tex.outputs['Alpha'])

      if self.material is not None:
         self.object.data.materials.append(self.material)
      return self.material

   def loadShader(self, shader):
      shader.parse()
      loadStart = time.process_time()
      bsdf = self.material.node_tree.nodes["Principled BSDF"]

      i = 0
      for ripNode in shader.nodes:
         node = self.createShaderNode(ripNode)
         x = -2000 + 600 * floor(i / 100)
         y = 1000 - 40 * (i % 100)
         node.location = [x,y]
         i += 1

      x = -2000 + 600 * floor(i / 100)
      y = 1000 - 40 * (i % 100)
      bsdf.location = [x,y]

      basecolor = self.material.node_tree.nodes.new("ShaderNodeCombineRGB")
      basecolor.hide = True
      basecolor.location = [bsdf.location[0]-170, bsdf.location[1]-100]
      self.material.node_tree.links.new(bsdf.inputs['Base Color'], basecolor.outputs[0])
      self.material.node_tree.links.new(bsdf.inputs['Subsurface Color'], basecolor.outputs[0])
      self.createNodeChain(shader.registers['o1']['x'], basecolor, 0)
      self.createNodeChain(shader.registers['o1']['y'], basecolor, 1)
      self.createNodeChain(shader.registers['o1']['z'], basecolor, 2)

      rro1w = self.material.node_tree.nodes.new("NodeReroute")
      rro1w.location = [bsdf.location[0]-80, bsdf.location[1]-140]
      self.createNodeChain(shader.registers['o1']['w'], rro1w, 0)

      rro3x = self.material.node_tree.nodes.new("NodeReroute")
      rro3x.location = [bsdf.location[0]-80, bsdf.location[1]-180]
      self.createNodeChain(shader.registers['o3']['x'], rro3x, 0)
      self.material.node_tree.links.new(bsdf.inputs['Subsurface'], rro3x.outputs[0])

      sssradius = self.material.node_tree.nodes.new("ShaderNodeCombineXYZ")
      sssradius.hide = True
      sssradius.location = [bsdf.location[0]-170, bsdf.location[1]-220]
      self.material.node_tree.links.new(bsdf.inputs['Subsurface Radius'], sssradius.outputs[0])
      self.createNodeChain(shader.registers['o3']['y'], sssradius, 0)
      self.createNodeChain(shader.registers['o3']['z'], sssradius, 1)
      self.createNodeChain(shader.registers['o3']['w'], sssradius, 2)

      rro2x = self.material.node_tree.nodes.new("NodeReroute")
      rro2y = self.material.node_tree.nodes.new("NodeReroute")
      rro2z = self.material.node_tree.nodes.new("NodeReroute")
      rro2w = self.material.node_tree.nodes.new("NodeReroute")
      rro2x.location = [bsdf.location[0]-80, bsdf.location[1]-260]
      rro2y.location = [bsdf.location[0]-80, bsdf.location[1]-300]
      rro2z.location = [bsdf.location[0]-80, bsdf.location[1]-340]
      rro2w.location = [bsdf.location[0]-80, bsdf.location[1]-380]
      self.createNodeChain(shader.registers['o2']['x'], rro2x, 0)
      self.createNodeChain(shader.registers['o2']['y'], rro2y, 0)
      self.createNodeChain(shader.registers['o2']['z'], rro2z, 0)
      self.createNodeChain(shader.registers['o2']['w'], rro2w, 0)
      self.material.node_tree.links.new(bsdf.inputs['Roughness'], rro2x.outputs[0])
      self.material.node_tree.links.new(bsdf.inputs['Specular'], rro2y.outputs[0])
      self.material.node_tree.links.new(bsdf.inputs['Metallic'], rro2z.outputs[0])

      normal = self.material.node_tree.nodes.new("ShaderNodeNormalMap")
      normal.hide = True
      normal.location = [bsdf.location[0]-170, bsdf.location[1]-515]
      self.material.node_tree.links.new(bsdf.inputs['Normal'], normal.outputs[0])
      normalcolor = self.material.node_tree.nodes.new("ShaderNodeCombineXYZ")
      normalcolor.hide = True
      normalcolor.location = [bsdf.location[0]-270, bsdf.location[1]-515]
      self.material.node_tree.links.new(normal.inputs['Color'], normalcolor.outputs[0])
      self.createNodeChain(shader.registers['o0']['x'], normalcolor, 0)
      self.createNodeChain(shader.registers['o0']['y'], normalcolor, 1)

      rro0z = self.material.node_tree.nodes.new("NodeReroute")
      rro0w = self.material.node_tree.nodes.new("NodeReroute")
      rro0z.location = [bsdf.location[0]-80, bsdf.location[1]-555]
      rro0w.location = [bsdf.location[0]-80, bsdf.location[1]-595]
      self.createNodeChain(shader.registers['o0']['z'], rro0z, 0)
      self.createNodeChain(shader.registers['o0']['w'], rro0w, 0)

      loadTime = time.process_time() - loadStart
      print("{} ({}): Material creation took {}s".format(self.ripFile.fileLabel, shader.fileName, loadTime))

   def createNodeChain(self, ripNodeOutput, previousNode, inputId):
      '''Create the entire chain of nodes that ends with the given node.

      Parameters
      ----------
      ripNodeOutput : RipNodeOutput
         the simulated output that we need to create a node for and then connect to the input
      previousNode : bpy.types.ShaderNode
         the existing node who inputs we need to link
      inputId : int or str
         the id of the input of previousNode that we are creating a link for
      '''

      ripNode = ripNodeOutput.node
      if ripNode.blenderNode is None:
         createShaderNode(self, ripNode)
         ripNode.blenderNode.location = [previousNode.location[0]-170, previousNode.location[1]+int(inputId)*40]
      self.material.node_tree.links.new(previousNode.inputs[inputId], ripNode.blenderNode.outputs[ripNodeOutput.id])
      if not ripNode.handled:
         for id in ripNode.inputs:
            if ripNode.inputs[id].connection is not None:
               self.createNodeChain(ripNode.inputs[id].connection, ripNode.blenderNode, id)
            else:
               ripNode.blenderNode.inputs[id].default_value = ripNode.inputs[id].defaultValue
         ripNode.handled = True

   def createShaderNode(self, ripNode):
      ripNode.blenderNode = self.material.node_tree.nodes.new("ShaderNode"+ripNode.type)
      ripNode.blenderNode.hide = True
      for prop in ripNode.options:
         if prop in ['name','label','operation','use_clamp']:
            setattr(ripNode.blenderNode, prop, ripNode.options[prop])
      if "imageData" in ripNode.options:
         ripNode.blenderNode.image = bpy.data.images.load(ripNode.options['imageData']['filePath'], check_existing=True)
         ripNode.blenderNode.image.colorspace_settings.is_data = True
         ripNode.blenderNode.image.colorspace_settings.name = "Non-Color"
      return ripNode.blenderNode

   def delete(self):
      bpy.data.objects.remove(self.object)
      bpy.data.meshes.remove(self.mesh)
