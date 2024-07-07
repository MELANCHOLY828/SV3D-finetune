"""Blender script to render images of 3D models.

This script is used to render images of 3D models. It takes in a list of paths
to .glb files and renders images of each model. The images are from rotating the
object around the origin. The images are saved to the output directory.

Example usage:
    blender -b -P blender_script_.py -- \
        --object_path my_object.glb \
        --object_json_path input_model_paths.json \
        --output_dir ./views \
        --engine CYCLES \
        --scale 0.8 \
        --num_images 12 \
        --camera_dist 1.2

Here, input_model_paths.json is a json file containing a list of paths to .glb.
"""

import argparse
import json
import math
import os
import random
import sys
import time
import urllib.request
import uuid
from typing import Tuple
from mathutils import Vector, Matrix
import numpy as np

import bpy
from mathutils import Vector


parser = argparse.ArgumentParser()
parser.add_argument(
    "--object_path",
    type=str,
    required=True,
    help="Path to the object file",
)
parser.add_argument(
    "--object_json_path",
    type=str,
    help="Path to the object json file",
    default=None,
)
parser.add_argument(
    "--valid_json_path",
    type=str,
    help="valid object json file",
    default=None,
)
parser.add_argument("--output_dir", type=str, default="~/.objaverse/hf-objaverse-v1/views_whole_sphere")
parser.add_argument(
    "--engine", type=str, default="CYCLES", choices=["CYCLES", "BLENDER_EEVEE"]
)
parser.add_argument("--scale", type=float, default=0.8)
parser.add_argument("--num_images", type=int, default=8)
parser.add_argument("--camera_dist", type=float, default=1.2)
    
argv = sys.argv[sys.argv.index("--") + 1 :]
args = parser.parse_args(argv)

print('===================', args.engine, '===================')

context = bpy.context
scene = context.scene
render = scene.render

cam = scene.objects["Camera"]
cam.location = (0, 1.2, 0) # the initial position of the camera
cam.data.lens = 35
cam.data.sensor_width = 32

cam_constraint = cam.constraints.new(type="TRACK_TO")
cam_constraint.track_axis = "TRACK_NEGATIVE_Z"
cam_constraint.up_axis = "UP_Y"

# setup lighting
def set_lighting_specific():
    # bpy.ops.object.light_add(type="AREA")
    # light2 = bpy.data.lights["Area"]
    # light2.energy = 3000
    # bpy.data.objects["Area"].location[2] = 10 #0.5
    # bpy.data.objects["Area"].scale[0] = 100
    # bpy.data.objects["Area"].scale[1] = 100
    # bpy.data.objects["Area"].scale[2] = 100
    # 
    # 设置光源的能量和位置列表
    light_energy = 750
    dis = 10
    light_positions = [
        (10, 0, 10),
        (-10, 0, 10),
        (0, 10, 10),
        (0, -10, 10),
        (10, 10, 10),
        (-10, -10, 10),
        (10, -10, 10),
        (-10, 10, 10),
        (10, 0, -10),
        (-10, 0, -10),
        (0, 10, -10),
        (0, -10, -10),
        (10, 10, -10),
        (-10, -10, -10),
        (10, -10, -10),
        (-10, 10, -10),
    ]
    # 
    # 添加多个AREA光源并配置
    for i, pos in enumerate(light_positions):
        bpy.ops.object.light_add(type='AREA', location=pos)
        light_obj = bpy.context.object  # 获取新添加的光源对象
        if pos[2] < 0:
            light_obj.rotation_euler = (math.radians(180), 0, 0)  # 将光源朝向正Z方向
        light = light_obj.data  # 获取光源数据
        light.energy = light_energy
        light_obj.scale = (100, 100, 100)  # 设置光源尺寸
        light.color = (1.0, 1.0, 1.0)  # 白色光
        light.shadow_soft_size = 1.0  # 阴影柔化
    # 
    print("Added multiple AREA lights for uniform illumination.")
    # 
    # 打印所有光源的名称以验证
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT':
            print(f"Light name: {obj.name}, Location: {obj.location}, Energy: {obj.data.energy}")


def set_bg_lighting():
    # 设置背景颜色作为环境光源
    bpy.context.scene.world.use_nodes = True
    env_node_tree = bpy.context.scene.world.node_tree

    # 清除现有节点
    for node in env_node_tree.nodes:
        env_node_tree.nodes.remove(node)

    # 创建新的背景节点
    bg_node = env_node_tree.nodes.new(type='ShaderNodeBackground')
    bg_node.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)  # 白色背景
    bg_node.inputs['Strength'].default_value = 0.8  # 根据需要调整强度

    # 创建输出节点
    output_node = env_node_tree.nodes.new(type='ShaderNodeOutputWorld')

    # 连接背景节点到输出节点
    env_node_tree.links.new(bg_node.outputs['Background'], output_node.inputs['Surface'])

    print("Environment light set using background color.")

set_bg_lighting()

render.engine = args.engine
render.image_settings.file_format = "PNG"
render.image_settings.color_mode = "RGBA"
render.resolution_x = 576 # here the solution of the image
render.resolution_y = 576 # here resolution
render.resolution_percentage = 100

scene.cycles.device = "GPU"
scene.cycles.samples = 128
scene.cycles.diffuse_bounces = 1
scene.cycles.glossy_bounces = 1
scene.cycles.transparent_max_bounces = 3
scene.cycles.transmission_bounces = 3
scene.cycles.filter_width = 0.01
scene.cycles.use_denoising = True
scene.render.film_transparent = True

bpy.context.preferences.addons["cycles"].preferences.get_devices()
# Set the device_type
bpy.context.preferences.addons[
    "cycles"
].preferences.compute_device_type = "CUDA" # or "OPENCL"

def randomize_camera(radius=1.2, rk_img=0, num_img=21):
    theta = rk_img / num_img * 2 * math.pi + random.uniform(-math.pi / 50, math.pi / 50) # random here to make the image more diverse
    
    # phi采样
    phi_min = -math.pi / 18 + math.pi / 2  # -10 degrees in radians
    phi_max = math.pi / 18 + math.pi / 2  # 10 degrees in radians
    phi = random.uniform(phi_min, phi_max)

    radius = radius + random.uniform(-0.1, 0.1)
    x = radius * math.sin(phi) * math.cos(theta)
    y = radius * math.sin(phi) * math.sin(theta)
    z = radius * math.cos(phi)
    
    camera = bpy.data.objects["Camera"]
    camera.location = (x, y, z)

    direction = - camera.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    camera.rotation_euler = rot_quat.to_euler()
    return camera

def randomize_lighting() -> None:
    light2.energy = random.uniform(300, 600)
    bpy.data.objects["Area"].location[0] = random.uniform(-1., 1.)
    bpy.data.objects["Area"].location[1] = random.uniform(-1., 1.)
    bpy.data.objects["Area"].location[2] = random.uniform(0.5, 1.5)


def reset_lighting() -> None:
    light2.energy = 1000
    bpy.data.objects["Area"].location[0] = 0
    bpy.data.objects["Area"].location[1] = 0
    bpy.data.objects["Area"].location[2] = 0.5


def reset_scene() -> None:
    """Resets the scene to a clean state."""
    # delete everything that isn't part of a camera or a light
    for obj in bpy.data.objects:
        if obj.type not in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    # delete all the materials
    for material in bpy.data.materials:
        bpy.data.materials.remove(material, do_unlink=True)
    # delete all the textures
    for texture in bpy.data.textures:
        bpy.data.textures.remove(texture, do_unlink=True)
    # delete all the images
    for image in bpy.data.images:
        bpy.data.images.remove(image, do_unlink=True)


# load the glb model
def load_object(object_path: str) -> None:
    """Loads a glb model into the scene."""
    if object_path.endswith(".glb"):
        bpy.ops.import_scene.gltf(filepath=object_path, merge_vertices=True)
    elif object_path.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=object_path)
    else:
        raise ValueError(f"Unsupported file type: {object_path}")


def scene_bbox(single_obj=None, ignore_matrix=False):
    bbox_min = (math.inf,) * 3
    bbox_max = (-math.inf,) * 3
    found = False
    for obj in scene_meshes() if single_obj is None else [single_obj]:
        found = True
        for coord in obj.bound_box:
            coord = Vector(coord)
            if not ignore_matrix:
                coord = obj.matrix_world @ coord
            bbox_min = tuple(min(x, y) for x, y in zip(bbox_min, coord))
            bbox_max = tuple(max(x, y) for x, y in zip(bbox_max, coord))
    if not found:
        raise RuntimeError("no objects in scene to compute bounding box for")
    return Vector(bbox_min), Vector(bbox_max)


def scene_root_objects():
    for obj in bpy.context.scene.objects.values():
        if not obj.parent:
            yield obj


def scene_meshes():
    for obj in bpy.context.scene.objects.values():
        if isinstance(obj.data, (bpy.types.Mesh)):
            yield obj

# function from https://github.com/panmari/stanford-shapenet-renderer/blob/master/render_blender.py
def get_3x4_RT_matrix_from_blender(cam):
    # bcam stands for blender camera
    # R_bcam2cv = Matrix(
    #     ((1, 0,  0),
    #     (0, 1, 0),
    #     (0, 0, 1)))

    # Transpose since the rotation is object rotation, 
    # and we want coordinate rotation
    # R_world2bcam = cam.rotation_euler.to_matrix().transposed()
    # T_world2bcam = -1*R_world2bcam @ location
    #
    # Use matrix_world instead to account for all constraints
    location, rotation = cam.matrix_world.decompose()[0:2]
    R_world2bcam = rotation.to_matrix().transposed()

    # Convert camera location to translation vector used in coordinate changes
    # T_world2bcam = -1*R_world2bcam @ cam.location
    # Use location from matrix_world to account for constraints:     
    T_world2bcam = -1*R_world2bcam @ location

    # # Build the coordinate transform matrix from world to computer vision camera
    # R_world2cv = R_bcam2cv@R_world2bcam
    # T_world2cv = R_bcam2cv@T_world2bcam

    # put into 3x4 matrix
    RT = Matrix((
        R_world2bcam[0][:] + (T_world2bcam[0],),
        R_world2bcam[1][:] + (T_world2bcam[1],),
        R_world2bcam[2][:] + (T_world2bcam[2],)
        ))
    return RT

def normalize_scene():
    bbox_min, bbox_max = scene_bbox()
    scale = 1 / max(bbox_max - bbox_min)
    for obj in scene_root_objects():
        obj.scale = obj.scale * scale
    # Apply scale to matrix_world.
    bpy.context.view_layer.update()
    bbox_min, bbox_max = scene_bbox()
    offset = -(bbox_min + bbox_max) / 2
    for obj in scene_root_objects():
        obj.matrix_world.translation += offset
    bpy.ops.object.select_all(action="DESELECT")


def save_images(object_file: str) -> None:
    """Saves rendered images of the object in the scene."""
    os.makedirs(args.output_dir, exist_ok=True)

    reset_scene()

    # load the object
    load_object(object_file)
    object_uid = os.path.basename(object_file).split(".")[0]
    normalize_scene()

    # create an empty object to track
    empty = bpy.data.objects.new("Empty", None)
    scene.collection.objects.link(empty)
    cam_constraint.target = empty

    # randomize_lighting()
    for i in range(args.num_images):

        # set camera position and rotation then save them
        # save the first camera position
        camera = randomize_camera(args.camera_dist, i, args.num_images)
            
        # render the image
        render_path = os.path.join(args.output_dir, object_uid, f"{i:03d}.png")
        scene.render.filepath = render_path
        bpy.ops.render.render(write_still=True)

        # save camera RT matrix
        RT = get_3x4_RT_matrix_from_blender(camera)
        RT_path = os.path.join(args.output_dir, object_uid, f"{i:03d}.npy")
        np.save(RT_path, RT)

        # save camera position by .txt
        # cam_pos_path = os.path.join(args.output_dir, object_uid, f"{i:03d}.txt")
        # data = {
        # "position": {
        #     "x": camera.location.x,
        #     "y": camera.location.y,
        #     "z": camera.location.z
        #     }
        # }
        # with open(cam_pos_path, 'w') as file:
        #     json.dump(data, file, indent=4)
        
        
def download_object(object_url: str) -> str:
    """Download the object and return the path."""
    # uid = uuid.uuid4()
    uid = object_url.split("/")[-1].split(".")[0]
    tmp_local_path = os.path.join("tmp-objects", f"{uid}.glb" + ".tmp")
    local_path = os.path.join("tmp-objects", f"{uid}.glb")
    # wget the file and put it in local_path
    os.makedirs(os.path.dirname(tmp_local_path), exist_ok=True)
    urllib.request.urlretrieve(object_url, tmp_local_path)
    os.rename(tmp_local_path, local_path)
    # get the absolute path
    local_path = os.path.abspath(local_path)
    return local_path


def append_to_json_file(file_path, new_data):
    # Check if the file exists
    
    if os.path.exists(file_path):
        # Read the existing data
        with open(file_path, "r") as f:
            data = json.load(f)
    else:
        data = []

    # Append the new data and remove duplicates
    data_set = set(data)
    new_data_set = set(new_data)
    combined_data_set = data_set.union(new_data_set)

    # Convert the set back to a list
    combined_data = list(combined_data_set)

    # Write the updated data back to the file
    with open(file_path, "w") as f:
        json.dump(combined_data, f, indent=2)


def process(object_path: str, valid_paths=None):
    try:
        start_i = time.time()
        if object_path.startswith("http"):
            local_path = download_object(object_path)
        else:
            local_path = object_path
        save_images(local_path)
        end_i = time.time()
        # print("Finished", local_path, "in", end_i - start_i, "seconds")
        # delete the object if it was downloaded
        if object_path.startswith("http"):
            os.remove(local_path)
        
        valid_paths.append(object_path) if valid_paths is not None else None
            
    except Exception as e:
        print("Failed to render", object_path)
        print(e)
        

if __name__ == "__main__":
    
    valid_paths = []
    
    # the objects to process
    if args.object_json_path:
        with open(args.object_json_path) as f:
            object_paths = json.load(f)
        for object_path in object_paths:
            process(object_path, valid_paths)
        
        valid_json_path = args.valid_json_path if args.valid_json_path else "valid_paths.json"
           
        append_to_json_file(valid_json_path, valid_paths) 
        

    else:
        process(args.object_path, valid_paths)
        valid_json_path = args.valid_json_path if args.valid_json_path else "valid_paths.json"
           
        append_to_json_file(valid_json_path, valid_paths) 