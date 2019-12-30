import colorsys
from contextlib import contextmanager
from typing import Sequence

import bpy
import numpy as np

from bubble_chamber_bpy.models import BubbleChamber, Particle
from bubble_chamber_bpy.simulation import Simulation


def clear_all():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.context.scene.frame_set(0)


def create_chamber(chamber: BubbleChamber):
    print("Creating bubble chamber")
    size = np.max(chamber.dimensions)
    bpy.ops.mesh.primitive_cube_add(size=size, location=(0, 0, 0))
    chamber_bpy = bpy.context.object
    chamber_bpy.name = "Chamber"
    chamber_bpy.display_type = "WIRE"
    chamber_bpy.hide_render = True

    # Add a force field to influence the particles:
    bpy.ops.object.effector_add(type="TURBULENCE", radius=size, location=(0, 0, 0))
    field = bpy.context.object
    field.name = "Turbulence and Flow"
    field.field.flow = 5.0

    # Smoke effects:
    # bpy.ops.object.quick_smoke()
    # smoke_dom = bpy.data.objects["Smoke Domain"]
    # smoke_dom.location = (0, 0, 0)
    # smoke_dom.scale = chamber.dimensions / 2
    # smk = smoke_dom.modifiers["Smoke"]
    # Smoke shouldn't rise or fall:
    # smk.domain_settings.beta = 0.0
    # smk.domain_settings.resolution_max = 64
    # smk.domain_settings.use_high_resolution = True

    # Quick smoke added an emitter to the chamber itself, remove it:
    # chamber_bpy.select_set(True)
    # bpy.context.view_layer.objects.active = chamber_bpy
    # bpy.ops.object.modifier_remove(modifier="Smoke")

    # Add smoke domain to the chamber:
    # bpy.ops.object.modifier_add(type="SMOKE")
    # smk = chamber_bpy.modifiers["Smoke"]
    # smk.smoke_type = "DOMAIN"
    # Smoke shouldn't rise or fall:
    # smk.domain_settings.beta = 0.0

    # The chamber itself should be transparent, otherwise we can't look inside:
    # mat = bpy.data.materials.new(name="Smoke Domain Material")
    # mat.diffuse_color = (0.0, 0.0, 0.0, 0.0)
    # chamber_bpy.data.materials.append(mat)


def create_particles(particles: Sequence[Particle]):
    print("Creating particles")
    for i, p in enumerate(particles):
        get_or_create_particle(p, i)


def create_world():
    world = bpy.data.worlds["World"]
    world.use_nodes = False
    world.color = (0, 0, 0)


def create_camera(chamber: BubbleChamber):
    print("Creating camera")
    # TODO: Make this less random:
    bpy.ops.object.camera_add(location=(0, 0, chamber.dimensions[2] * 2))
    cam = bpy.context.object
    bpy.context.scene.camera = cam


def create_vapor_particle():
    print("Creating vapor particle")
    bpy.ops.mesh.primitive_cube_add()
    vapor_part = bpy.context.object
    vapor_part.name = "Vapor"
    vapor_part.hide_viewport = True
    vapor_part.hide_render = True


def create_light(chamber: BubbleChamber):
    print("Creating light")
    bpy.ops.object.light_add(type="SUN", location=(0, 0, chamber.dimensions[2]))


def run_simulation(simulation: Simulation):
    FPS = 30

    simulation.start()
    frame = 0
    while any(p.is_dirty for p in simulation.particles):
        # Advance the simulation by 1 step:
        simulation.step()

        # Current frame is the total time passed in sim * FPS
        frame = int(simulation.time_passed * FPS)
        bpy.context.scene.frame_set(frame)

        for i, p in enumerate(simulation.particles):
            obj = get_or_create_particle(p, i)

            if p.is_alive:
                set_visibility(obj, True)
                obj.location = p.position
                obj.keyframe_insert(data_path="location")
            elif p.is_dirty:
                p.is_dirty = False
                obj.location = p.position
                obj.keyframe_insert(data_path="location")
                set_visibility(obj, False)
                obj.particle_systems[
                    0
                ].settings.frame_end = bpy.context.scene.frame_current


def get_or_create_particle(p: Particle, i: int):
    name = f"Particle {i}"
    obj = bpy.data.objects.get(name)

    if not obj:
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.01, location=p.position)
        obj = bpy.context.object
        obj.name = name

        # Ensure the particle is visible starting at this frame:
        obj.location = p.position
        obj.keyframe_insert(data_path="location")
        # obj.hide_viewport = False
        # obj.keyframe_insert(data_path="hide_viewport")
        with at_frame(0):
            set_visibility(obj, False)
        set_visibility(obj, True)

        # Assign the material:
        mat = get_or_create_material(p)
        obj.data.materials.append(mat)

        # Particle system:
        bpy.ops.object.particle_system_add()
        particles = obj.particle_systems[0]
        particles.name = f"{name} Particles"
        particles.settings.frame_start = bpy.context.scene.frame_current
        particles.settings.particle_size = 0.01
        particles.settings.size_random = 0.5
        particles.settings.lifetime = 1000.0
        particles.settings.effector_weights.gravity = 0.0
        particles.settings.render_type = "OBJECT"
        particles.settings.instance_object = bpy.data.objects["Vapor"]

        # Add smoke
        # bpy.ops.object.modifier_add(type="SMOKE")
        # smk = obj.modifiers["Smoke"]
        # smk.smoke_type = "FLOW"
        # smk.flow_settings.smoke_color = color_for_particle(p, False)

    return obj


def get_or_create_material(p: Particle):
    name = "Material Particle"

    obj = bpy.data.materials.new(name=name)
    obj.use_nodes = True

    # Add an emission node:
    node_tree = obj.node_tree
    material_out = node_tree.nodes["Material Output"]

    # Delete default shader node:
    for n in node_tree.nodes:
        if n != material_out:
            node_tree.nodes.remove(n)

    emission = node_tree.nodes.new(type="ShaderNodeEmission")
    emission.inputs["Color"].default_value = color_for_particle(p)
    node_tree.links.new(
        emission.outputs[0], node_tree.get_output_node(target="ALL").inputs[0]
    )

    return obj


def color_for_particle(p: Particle, with_alpha: bool = True):
    charge = p.total_charge
    hue = 0 if charge >= 0 else 0.7
    saturation = abs(charge) / p.mass
    value = 0.7
    rgb = colorsys.hsv_to_rgb(hue, saturation, value)

    if with_alpha:
        alpha = 1.0
        return (*rgb, alpha)
    else:
        return rgb


def set_visibility(obj, vis: bool):
    hide = not vis
    if obj.hide_render != hide:
        obj.hide_render = hide
        obj.keyframe_insert(data_path="hide_render")


@contextmanager
def at_frame(frame: int):
    current_frame = bpy.context.scene.frame_current
    bpy.context.scene.frame_set(frame)
    yield
    bpy.context.scene.frame_set(current_frame)
