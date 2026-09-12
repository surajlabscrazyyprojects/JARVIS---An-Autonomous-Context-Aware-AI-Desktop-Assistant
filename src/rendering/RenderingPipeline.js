/**
 * RenderingPipeline — AAA character rendering system.
 *
 * Features in this version:
 *  - DETERMINISTIC normalization: bounding box computed every load in WORLD space
 *    after matrixWorld update. Root transforms are reset before measuring, cached
 *    transforms are cleared, and NO previous model transform is ever reused.
 *    Spider-Man keeps identical scale after ANY number of switches.
 *  - Universal framing: every character lands at the same center, same feet
 *    position, same viewport height, same camera distance, same eye level.
 *    No manual offsets — pure automatic bounding-box normalization.
 *  - Cinematic slide transition: outgoing slides out opposite direction with
 *    slight rotation and opacity fade; incoming slides in from selected direction,
 *    ease-out with slight overshoot, fades in, settles naturally. 450–600 ms.
 *  - Shared idle rotation controller — one controller, every character identical.
 *  - Hologram pipeline for EVERY character: blue hologram, animated scanlines,
 *    Fresnel glow, edge glow, pulse, transparent energy, animated emissive.
 *  - Wireframe pipeline for EVERY character: cyan glowing lines, transparent
 *    interior, animated opacity, moving scanline, emissive bloom.
 *  - Premium lighting: HDR, ACES Filmic tone mapping, sRGB, PMREM environment,
 *    directional key + hemisphere + ambient + fill + back rim, soft shadows,
 *    strong blue hologram lab theme. Texture mode restores original lighting.
 *  - Material polish: metalness boost, clearcoat/specular where supported,
 *    envMapIntensity raised for premium metallic reflections.
 *  - Smooth mode switching: 250 ms fade between Texture/Hologram/Wireframe.
 */

import { getCharacterProfile } from '../config/characters.js';

// RoomEnvironment must be imported explicitly — it is NOT a core THREE export.
// Without it, scene.environment stays null and metalness=1.0 surfaces reflect
// nothing (rendered pure black) — the root cause of dark/black metallic models.
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const PREFIX = '[RenderingPipeline]';

// Every character is normalized to this world-space height (metres).
const TARGET_HEIGHT = 2.2;

// Camera: model should fill ~68 % of viewport height.
const VIEWPORT_FILL = 0.68;

// Slide transition duration in ms (450–600).
const SLIDE_MS = 560;

// Slide travel distance in world units.
const SLIDE_DIST = 3.5;

// Slide rotation during exit/enter (radians).
const SLIDE_ROTATION = 0.18;

// Mode fade duration.
const MODE_FADE_MS = 250;

export const RENDER_MODE = {
  HOLOGRAM:  'hologram',
  TEXTURE:   'texture',
  WIREFRAME: 'wireframe',
};

export class RenderingPipeline {
  constructor({ scene, camera, renderer, pivot, THREE }) {
    this.scene    = scene;
    this.camera   = camera;
    this.renderer = renderer;
    this.pivot    = pivot;
    this.THREE    = THREE;

    this.mode           = RENDER_MODE.HOLOGRAM;
    this.materialCache  = new Map(); // id → { meshList, original, hologram, wireframe, state }
    this.characterRoots = new Map(); // id → model
    this.activeId       = null;
    this.rotationY      = 0;
    this.rotationSpeed  = 0.28;
    this.autoRotate     = true;

    // Shared user transform — ONE controller for EVERY character (mouse + hand).
    // No per-character code: all models (including Thanos) receive identical input.
    this.userYaw    = 0;
    this.userPitch  = 0;
    this.userScale  = 1;
    this.userPanX   = 0;
    this.userPanY   = 0;
    this.cameraZoom = 1;
    this._currentUserScale = 1;
    this._lastCamZoom = 1;
    this._lastPanX = 0;
    this._lastPanY = 0;

    // Slide animation state
    this._slide = null; // active slide animator

    // Right-drag "follow the mouse" preview offset (character switch swipe).
    // While the user drags, the active character translates horizontally
    // with the cursor; on release it either springs back or the slide
    // transition takes over.
    this.dragOffsetX = 0;
    this._dragOffsetXTarget = 0;

    // Persistent user-controlled position offset for the active character,
    // driven by the HUD "Move Character" sliders / free-control drag.
    this.userOffsetX = 0;
    this.userOffsetY = 0;

    // Mode fade state
    this._modeFade = null; // { startMs, fromMode, toMode, cache }

    // Hologram projection light cone — a beam of light rising from the floor
    // beneath the character (like the classic Iron Man hologram projector).
    // Only a light beam: NO base / pedestal mesh, per request.
    this._holoLight = null; // THREE.Group of beam meshes
    this._holoTime  = 0;    // shared clock driving the beam shaders

    this._lights   = [];
    this._envSetup = false;
    this._fadeTinker = 0;

    // Pre-allocated reusable vectors/boxes to eliminate per-frame allocations (0 GC overhead)
    this._scratchBox    = new THREE.Box3();
    this._scratchVec1   = new THREE.Vector3();
    this._scratchVec2   = new THREE.Vector3();
    this._scratchVec3   = new THREE.Vector3();
    this._targetCamPos  = new THREE.Vector3(0, 1.2, 5);
    this._targetCamLook = new THREE.Vector3(0, 0.8, 0);
    this._currentCamLook= new THREE.Vector3(0, 0.8, 0);
    this._hasCamTarget  = false;

    this._setupRenderer();
    this._setupLighting(this.mode);
    this._createHologramLight();
  }

  /* ================================================================ */
  /*  Renderer                                                         */
  /* ================================================================ */

  _setupRenderer() {
    if (!this.renderer || !this.THREE) return;
    const r = this.renderer;
    r.outputColorSpace    = this.THREE.SRGBColorSpace;
    r.toneMapping         = this.THREE.ACESFilmicToneMapping;
    // Keep the user-facing brightness at 100% (1.0).  Higher exposure makes
    // the hologram look washed out and no longer matches the HUD brightness
    // control.
    r.toneMappingExposure = 1.0;

    // Enable physically correct lighting (r155+). This is the root cause
    // of incorrect lighting on Hulk/Thor — legacy lights use a different
    // intensity model and produce washed-out / wrong PBR results.
    if ('useLegacyLights' in r) {
      r.useLegacyLights = false;
    }

    // High dynamic range lighting for premium metallic reflections.
    if (typeof r.toneMappingExposure === 'number') {
      r.toneMappingExposure = 1.0;
    }

    if (r.shadowMap) {
      r.shadowMap.enabled = true;
      r.shadowMap.type    = this.THREE.PCFSoftShadowMap;
    }
  }

  /* ================================================================ */
  /*  Public API                                                       */
  /* ================================================================ */

  /**
   * Register a loaded model: normalize, cache materials, apply current mode.
   * Called EVERY time a model is (re)attached so normalization is identical
   * on every load.
   */
  registerCharacter(characterId, model) {
    if (!model || !this.THREE) return;

    this._normalizeModel(model, characterId);
    // Dispose old cached materials before re-caching (avoid leaks)
    if (this.materialCache.has(characterId)) {
      this._disposeCache(characterId);
    }
    this._cacheMaterials(characterId, model);
    this._applyMode(characterId, this.mode);

    this.characterRoots.set(characterId, model);
    model.userData.characterId = characterId;

    console.log(`${PREFIX} Registered: ${characterId}`);
  }

  /**
   * Show characterId with a cinematic slide-in animation.
   * previousId slides out in the opposite direction with fade + rotation.
   * @param {number} [slideDir] Optional explicit slide direction:
   *   1 = incoming enters from the right (+X), -1 = from the left (-X).
   *   When omitted, it is derived from the character order (backwards
   *   compatible for nav buttons / boot).
   */
  showCharacter(characterId, previousId, slideDir) {
    const THREE = this.THREE;
    if (!THREE) return;

    // Cancel any in-flight slide
    if (this._slide) { this._slide.cancelled = true; this._slide = null; }

    const incoming = this.characterRoots.get(characterId);
    if (!incoming) return;

    const outgoing = previousId ? this.characterRoots.get(previousId) : null;

    // Skip if same model (first bootstrap or same character)
    if (incoming === outgoing) {
      incoming.visible = true;
      this.activeId = characterId;
      this._frameCamera(characterId);
      return;
    }

    // Determine slide direction based on character order
    const ORDER = ['IRON_MAN', 'SPIDER_MAN', 'THOR', 'THANOS'];
    const prevIdx = ORDER.indexOf(previousId);
    const nextIdx = ORDER.indexOf(characterId);
    // Explicit direction (from the swipe) wins; otherwise derive from order.
    // incoming comes from right (+X) if moving forward, left (-X) if backward
    const dir = (typeof slideDir === 'number')
      ? slideDir
      : ((nextIdx >= prevIdx || prevIdx === -1) ? 1 : -1);

    // Snap rotation so the slide is always axis-aligned
    this.rotationY = 0;
    this.characterRoots.forEach(m => { m.rotation.y = 0; m.rotation.x = 0; });

    this.activeId = characterId;

    // Hand the preview offset back to the slide transition
    this.dragOffsetX = 0;
    this._dragOffsetXTarget = 0;

    // Restore each model to its NORMALIZED base transform (scale + position).
    // The slide animation then offsets RELATIVE to this base — so centering
    // and scaling are never wiped out on switch (root-cause fix for
    // Spider-Man changing size / not centered).
    this._restoreNormalizedTransform(incoming);
    if (outgoing) this._restoreNormalizedTransform(outgoing);

    // Prepare incoming: start off-screen (relative to its normalized base)
    incoming.visible = true;
    incoming.position.x = incoming.userData.normalizedPosition?.x ?? 0;
    incoming.position.x += dir * SLIDE_DIST;

    // Prepare outgoing: start at rest (normalized base)
    if (outgoing) {
      outgoing.visible = true;
      outgoing.position.x = outgoing.userData.normalizedPosition?.x ?? 0;
    }

    // Hide all others except the two animating
    this.characterRoots.forEach((m, id) => {
      if (id !== characterId && id !== previousId) m.visible = false;
    });

    const slide = { cancelled: false, incoming, outgoing, dir, elapsed: 0 };
    this._slide = slide;

    this._frameCamera(characterId);
  }

  /* ================================================================ */
  /*  Easing                                                           */
  /* ================================================================ */

  _easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  _easeInQuad(t) {
    return t * t;
  }

  _easeOutBack(t, s = 1.2) {
    // Ease-out with slight overshoot
    const s2 = s;
    const t2 = t - 1;
    return 1 + (s2 + 1) * t2 * t2 * t2 + s2 * t2 * t2;
  }

  /**
   * Smoothly switch rendering mode with 250 ms cross-fade.
   * The fade is driven from the render loop (update) for zero stutter.
   */
  _getMaterialsForMode(cache, mode) {
    if (!cache) return null;
    if (mode === RENDER_MODE.TEXTURE || mode === 'original') return cache.original || cache.texture;
    if (mode === RENDER_MODE.HOLOGRAM) return cache.hologram;
    if (mode === RENDER_MODE.WIREFRAME) return cache.wireframe;
    return cache[mode] || cache.original || cache.texture;
  }

  /**
   * Smoothly switch rendering mode with 250 ms cross-fade.
   * The fade is driven from the render loop (update) for zero stutter.
   */
  setRenderingMode(mode) {
    if (!Object.values(RENDER_MODE).includes(mode)) return;
    if (mode === this.mode) return;

    const fromMode = this.mode;
    this.mode = mode;
    this._setupLighting(mode);

    // Animate material alpha cross-fade: old material fades out,
    // new material fades in over MODE_FADE_MS.
    if (this._modeFade) { this._modeFade.cancelled = true; }
    const fade = { elapsed: 0, fromMode, toMode: mode, cancelled: false };
    this._modeFade = fade;

    // Start from opacity 0 on new materials
    this.characterRoots.forEach((_, id) => {
      const cache = this.materialCache.get(id);
      if (!cache) return;
      const targetMats = this._getMaterialsForMode(cache, mode);
      if (!targetMats) return;
      cache.meshList.forEach((mesh, i) => {
        const targetMat = targetMats[i];
        if (targetMat) {
          mesh.material = targetMat;
          const mats = Array.isArray(targetMat) ? targetMat : [targetMat];
          mats.forEach(m => {
            if (!m) return;
            if (mode === RENDER_MODE.TEXTURE) {
              m.opacity = m.userData?.originalOpacity ?? 1.0;
              m.transparent = m.userData?.originalTransparent ?? false;
              m.depthWrite = m.userData?.originalDepthWrite ?? true;
            } else {
              m.opacity = 0;
              m.transparent = true;
              m.depthWrite = false;
            }
            m.needsUpdate = true;
          });
        }
      });
    });

    // Hologram light cone — cross-fade in/out with the render mode.
    if (this._holoLight) {
      const involvesHolo = fromMode === RENDER_MODE.HOLOGRAM || mode === RENDER_MODE.HOLOGRAM;
      if (involvesHolo) {
        this._holoLight.visible = true;
        // Fade IN from 0 when entering hologram, fade OUT from full when leaving
        this._setHoloLightOpacity(mode === RENDER_MODE.HOLOGRAM ? 0 : 1);
      } else {
        this._holoLight.visible = false;
      }
    }

    console.log(`${PREFIX} Mode → ${mode}`);
  }

  /**
   * Advance the active mode fade. Called every frame from update().
   */
  _updateModeFade(dt) {
    const fade = this._modeFade;
    if (!fade || fade.cancelled) return;

    fade.elapsed += dt * 1000;
    const t = Math.min(fade.elapsed / MODE_FADE_MS, 1);
    const eased = this._easeOutCubic(t);

    this.characterRoots.forEach((_, id) => {
      const cache = this.materialCache.get(id);
      if (!cache) return;
      const targetMats = this._getMaterialsForMode(cache, fade.toMode);
      if (!targetMats) return;
      cache.meshList.forEach((mesh, i) => {
        const targetMat = targetMats[i];
        if (!targetMat) return;
        const mats = Array.isArray(targetMat) ? targetMat : [targetMat];
        mats.forEach(m => {
          if (!m) return;
          const baseOp = fade.toMode === RENDER_MODE.TEXTURE ? (m.userData?.originalOpacity ?? 1.0) : (m.userData?.baseOpacity ?? 0.88);
          m.opacity = baseOp * eased;
          m.needsUpdate = true;
        });
      });
    });

    // Hologram light cone — fade in/out in sync with the character materials
    if (this._holoLight) {
      const toHolo   = fade.toMode === RENDER_MODE.HOLOGRAM;
      const fromHolo = fade.fromMode === RENDER_MODE.HOLOGRAM;
      if (toHolo || fromHolo) {
        this._holoLight.visible = true;
        this._setHoloLightOpacity(toHolo ? eased : (1 - eased));
      }
    }

    if (t >= 1) {
      // Finalize — set exact final opacity & depth states
      this.characterRoots.forEach((_, id) => {
        const cache = this.materialCache.get(id);
        if (!cache) return;
        const targetMats = this._getMaterialsForMode(cache, fade.toMode);
        if (!targetMats) return;
        cache.meshList.forEach((mesh, i) => {
          const targetMat = targetMats[i];
          if (!targetMat) return;
          const mats = Array.isArray(targetMat) ? targetMat : [targetMat];
          mats.forEach(m => {
            if (!m) return;
            if (fade.toMode === RENDER_MODE.TEXTURE) {
              m.opacity = m.userData?.originalOpacity ?? 1.0;
              m.transparent = m.userData?.originalTransparent ?? false;
              m.depthWrite = m.userData?.originalDepthWrite ?? true;
            } else {
              m.opacity = m.userData?.baseOpacity ?? 0.88;
              m.transparent = true;
              m.depthWrite = false;
            }
            m.needsUpdate = true;
          });
        });
      });
      // Finalize the hologram light cone visibility
      if (this._holoLight) {
        if (fade.toMode === RENDER_MODE.HOLOGRAM) {
          this._holoLight.visible = true;
          this._setHoloLightOpacity(1);
        } else {
          this._holoLight.visible = false;
          this._setHoloLightOpacity(0);
        }
      }

      this._modeFade = null;
    }
  }

  getRenderingMode() { return this.mode; }

  /**
   * Set the horizontal "drag preview" offset of the active character.
   * While the user right-drags to switch, the character follows the mouse.
   * Pass 0 to spring back (or to hand off to the slide transition).
   */
  setDragOffsetX(x) {
    this._dragOffsetXTarget = x || 0;
  }

  /** Called every frame from the animate loop. */
  update(dt) {
    if (!dt || !this.pivot) return;
    // Shared idle rotation controller — one controller for every character.
    if (this.autoRotate) this.rotationY += this.rotationSpeed * dt;
    // Apply rotation to EACH character model directly so they spin about their
    // OWN location (in place, free 360°), NOT about the scene pivot (which would
    // orbit them around the screen centre). The pivot is kept at identity and is
    // only used for the feet-planting scale (it sits at y=-0.5 in the HTML).
    this.pivot.rotation.set(0, 0, 0);
    this.characterRoots.forEach(model => {
      model.rotation.y = this.rotationY + this.userYaw;
      model.rotation.x = this.userPitch;
    });

    // Smooth user scale with damping (physics feel — no snapping).
    this._currentUserScale += (this.userScale - this._currentUserScale) * Math.min(1, dt * 8);
    // Scale each character about its OWN feet (model origin) so zooming grows
    // the character in place at its location — NOT about the screen-centre pivot.
    this.pivot.scale.set(1, 1, 1);
    this.characterRoots.forEach(model => {
      model.scale.set(this._currentUserScale, this._currentUserScale, this._currentUserScale);
    });

    // Hologram light cone: stays planted on the floor, scales with the
    // character (so the beam hugs the model when the user zooms), and
    // drives the beam shader clock for flicker / rising bands.
    if (this._holoLight) {
      const s = this._currentUserScale;
      this._holoLight.scale.set(s, s, s);
      this._holoTime += dt || 0;
      this._holoLight.traverse(obj => {
        if (obj.isMesh && obj.material && obj.material.uniforms && obj.material.uniforms.uTime) {
          obj.material.uniforms.uTime.value = this._holoTime;
        }
      });
    }

    // Smooth camera interpolation toward target position & lookAt (eliminates snapping & jitter)
    if (this._hasCamTarget && this.camera) {
      const lerpFactor = Math.min(1.0, dt * 6.0);
      this.camera.position.lerp(this._targetCamPos, lerpFactor);
      this._currentCamLook.lerp(this._targetCamLook, lerpFactor);
      this.camera.lookAt(this._currentCamLook);
    }

    // Re-frame camera only when zoom/pan changed (cheap guard — no per-frame cost)
    if (this.cameraZoom !== this._lastCamZoom ||
        this.userPanX !== this._lastPanX ||
        this.userPanY !== this._lastPanY) {
      this._lastCamZoom = this.cameraZoom;
      this._lastPanX = this.userPanX;
      this._lastPanY = this.userPanY;
      this._frameCamera(this.activeId);
    }

    // Stabilize the active character against accumulated numerical drift.
    if (this.activeId) {
      const activeModel = this.characterRoots.get(this.activeId);
      if (activeModel && activeModel.userData.normalizedPosition) {
        const normPos = activeModel.userData.normalizedPosition;
        // Y eases toward (base + user offset): sliders/free-drag move it.
        const targetY = normPos.y + this.userOffsetY;
        if (Math.abs(activeModel.position.y - targetY) > 0.0001) {
          activeModel.position.y += (targetY - activeModel.position.y) * 0.1;
        }
        if (Math.abs(activeModel.position.z - normPos.z) > 0.0001) {
          activeModel.position.z += (normPos.z - activeModel.position.z) * 0.1;
        }
        // Right-drag swipe preview: the character follows the cursor
        // horizontally (never during a slide — the slide owns X then).
        // Plus the persistent user X offset from the Move-Character sliders.
        if (!this._slide) {
          this.dragOffsetX += (this._dragOffsetXTarget - this.dragOffsetX) * Math.min(1, dt * 14);
          activeModel.position.x = normPos.x + this.dragOffsetX + this.userOffsetX;
        }
      }
    }

    // Drive slide + mode-fade transitions from the SAME render loop as the
    // main scene. This eliminates the stutter caused by separate
    // requestAnimationFrame loops that are not synchronized with the renderer.
    this._updateSlide(dt);
    this._updateModeFade(dt);
  }

  /**
   * Advance the active slide transition. Called every frame from update().
   * Uses delta-time so the animation is frame-rate independent and buttery.
   */
  _updateSlide(dt) {
    const slide = this._slide;
    if (!slide || slide.cancelled) return;

    slide.elapsed += dt * 1000;
    const t = Math.min(slide.elapsed / SLIDE_MS, 1);

    // Ease-out overshoot curve (easeOutBack with soft settle)
    const e = this._easeOutBack(t, 1.2);

    const { incoming, outgoing, dir } = slide;

    // Incoming: slide from ±SLIDE_DIST → 0 RELATIVE to its normalized base.
    // The base is the stored normalized position → centering/scaling preserved.
    const inBaseX = incoming.userData.normalizedPosition?.x ?? 0;
    incoming.position.x = inBaseX + dir * SLIDE_DIST * (1 - e);
    incoming.rotation.z = -dir * SLIDE_ROTATION * (1 - e);
    this._setModelOpacity(incoming, Math.min(1, t * 2.5));

    // Outgoing: slide from base → ∓SLIDE_DIST, rotate away, fade out
    if (outgoing && outgoing.parent) {
      const outBaseX = outgoing.userData.normalizedPosition?.x ?? 0;
      const outT = Math.min(t / 0.7, 1); // finish earlier
      outgoing.position.x = outBaseX - dir * SLIDE_DIST * this._easeInQuad(outT);
      outgoing.rotation.z = dir * SLIDE_ROTATION * this._easeInQuad(outT);
      this._setModelOpacity(outgoing, 1 - outT);
    }

    if (t >= 1) {
      // Settle back to normalized base
      incoming.position.x = inBaseX;
      incoming.rotation.z = 0;
      this._setModelOpacity(incoming, 1, true);

      if (outgoing && outgoing.parent) {
        outgoing.visible = false;
        this._restoreNormalizedTransform(outgoing);
      }
      this._slide = null;
    }
  }

  setAutoRotate(v) { this.autoRotate = v; }

  /**
   * Set the shared user transform (yaw, pitch, scale, pan). Applied to the
   * shared pivot every frame so ALL characters respond identically to mouse
   * and hand input.
   */
  setUserTransform(opts = {}) {
    if (typeof opts.yaw   === 'number') this.userYaw   = opts.yaw;
    if (typeof opts.pitch === 'number') this.userPitch = opts.pitch;
    if (typeof opts.scale === 'number') this.userScale = opts.scale;
    if (typeof opts.panX  === 'number') this.userPanX  = opts.panX;
    if (typeof opts.panY  === 'number') this.userPanY  = opts.panY;
  }

  /**
   * Set the shared camera zoom (mouse wheel). Identical for every character.
   */
  setCameraZoom(zoom) {
    this.cameraZoom = Math.max(0.4, Math.min(4, zoom || 1));
  }

  /**
   * Reset the shared user transform (double-click reset).
   */
  resetUserTransform() {
    this.userYaw = 0;
    this.userPitch = 0;
    this.userScale = 1;
    this.userPanX = 0;
    this.userPanY = 0;
    this.cameraZoom = 1;
    this._currentUserScale = 1;
    this._lastCamZoom = 1;
    this._lastPanX = 0;
    this._lastPanY = 0;
    this._frameCamera(this.activeId);
  }

  /* ================================================================ */
  /*  Deterministic Scale Normalizer                                   */
  /* ================================================================ */

  /**
   * Normalize model to TARGET_HEIGHT with identical center, feet, and
   * framing on EVERY load. Never reuses previous transforms.
   * Preserves the GLTF root rotation (essential for correct skinned-mesh
   * UV/texture alignment) and applies per-character position offsets.
   */
  _normalizeModel(model, characterId) {
    const THREE = this.THREE;
    if (!THREE) return;

    // 1. Repair NaN/zero transforms (rigged models, including Groups)
    this._repairTransforms(model);

    // 2. Detach from parent so WORLD == LOCAL space during measurement.
    //    This guarantees the pivot's live scale/rotation (from hand-tracking)
    //    NEVER corrupts the bounding-box measurement, centering, or scaling.
    //    The GLTF root rotation is preserved (critical for skinned-mesh
    //    texture/skeleton alignment).
    const parent = model.parent;
    if (parent) parent.remove(model);

    try {
      // 3. Reset scale + position ONLY — preserve the GLTF root rotation.
      //    Resetting the quaternion breaks skinned-mesh texture/skeleton
      //    alignment on glTF models that bake a Y-up→Z-up root rotation.
      model.scale.set(1, 1, 1);
      model.position.set(0, 0, 0);
      model.matrix.identity();
      model.matrixWorld.identity();
      model.updateMatrixWorld(true);

      // Clear any cached world matrices on descendants
      model.traverse(obj => {
        if (obj.matrixWorld) obj.matrixWorld.identity();
      });
      model.updateMatrixWorld(true);

      // 4. Bounding box — model is detached so world == local space.
      const box = new THREE.Box3().setFromObject(model);
      if (!this._isFiniteBox(box)) {
        console.error(`${PREFIX} ${characterId}: invalid bounding box`);
        return;
      }

      const size = box.getSize(new THREE.Vector3());
      // Height is the world-space Y extent. Fall back to tallest axis.
      let height = size.y;
      if (!isFinite(height) || height < 0.001) {
        height = Math.max(size.x, size.y, size.z);
      }

      // 5. Degenerate bounding box → log clear warning + safe fallback.
      if (!isFinite(height) || height < 0.001) {
        console.warn(
          `${PREFIX} ${characterId}: degenerate bounding box ` +
          `(${size.x.toFixed(3)}×${size.y.toFixed(3)}×${size.z.toFixed(3)}). ` +
          `Applying safe fallback scale 1.0 so the model stays visible.`
        );
        model.scale.set(1, 1, 1);
        model.position.set(0, 0, 0);
        return;
      }

      // 6. Scale uniformly so tallest axis = TARGET_HEIGHT
      const scale = TARGET_HEIGHT / height;
      model.scale.set(scale, scale, scale);
      model.updateMatrixWorld(true);

      // 7. Recompute bounding box after scale
      const box2   = new THREE.Box3().setFromObject(model);
      const center = box2.getCenter(new THREE.Vector3());

      // 8. Center on X/Z, ground-align on Y (feet at y=0)
      model.position.set(-center.x, -box2.min.y, -center.z);
      model.updateMatrixWorld(true);

      // 8b. Apply per-character position offset (e.g. Thanos nudge back)
      let offset = { x: 0, y: 0, z: 0 };
      try {
        const profile = getCharacterProfile(characterId);
        offset = profile?.positionOffset || profile?.model?.defaultPosition || offset;
      } catch (_) {}
      if (offset.x || offset.y || offset.z) {
        model.position.x += offset.x || 0;
        model.position.y += offset.y || 0;
        model.position.z += offset.z || 0;
        model.updateMatrixWorld(true);
      }

      // 8c. STORE the normalized transform so the slide animation can
      //     operate RELATIVE to it — never overwrite centering/scaling.
      //     This is the root-cause fix for "Spider-Man changes size after
      //     switching / not centered": the slide previously reset to
      //     identity, wiping the normalization on every switch.
      model.userData.normalizedScale    = model.scale.clone();
      model.userData.normalizedPosition = model.position.clone();

      // 9. Verify final bounding box
      const final = new THREE.Box3().setFromObject(model);
      const fs    = final.getSize(new THREE.Vector3());
      const fc    = final.getCenter(new THREE.Vector3());
      console.log(
        `${PREFIX} ${characterId}: scale=${scale.toFixed(4)} ` +
        `size=${fs.x.toFixed(2)}×${fs.y.toFixed(2)}×${fs.z.toFixed(2)} ` +
        `center=(${fc.x.toFixed(3)}, ${fc.y.toFixed(3)}, ${fc.z.toFixed(3)}) `
      );
    } finally {
      // 10. Always re-attach — even on error, model must remain in the scene.
      if (parent && !model.parent) parent.add(model);
      model.updateMatrixWorld(true);
    }
  }

  /**
   * Restore a model to its NORMALIZED base transform (the deterministic
   * scale + position computed by _normalizeModel). This preserves centering
   * and scaling across switches — the root-cause fix for Spider-Man changing
   * size / not centered after switching.
   *
   * If no normalized transform was stored (e.g. model never went through
   * _normalizeModel), fall back to identity (scale 1, position 0).
   *
   * Preserves GLTF root rotation — resetting it breaks skinned-mesh
   * texture/skeleton alignment. Only scale + position are restored.
   */
  _restoreNormalizedTransform(model) {
    if (!model) return;

    const s = model.userData.normalizedScale;
    const p = model.userData.normalizedPosition;
    if (s && p) {
      model.scale.copy(s);
      model.position.copy(p);
    } else {
      model.scale.set(1, 1, 1);
      model.position.set(0, 0, 0);
    }

    model.updateMatrixWorld(true);
  }

  _isFiniteBox(box) {
    return (
      isFinite(box.min.x) && isFinite(box.min.y) && isFinite(box.min.z) &&
      isFinite(box.max.x) && isFinite(box.max.y) && isFinite(box.max.z)
    );
  }

  _repairTransforms(model) {
    model.traverse(obj => {
      // Repair ALL objects — including Groups — not just bones/meshes.
      // A NaN/zero transform on a Group corrupts the entire subtree and
      // can make the whole model invisible (e.g. Thanos/Batman).
      const p = obj.position, s = obj.scale, q = obj.quaternion;
      if (p && (!isFinite(p.x) || !isFinite(p.y) || !isFinite(p.z))) p.set(0, 0, 0);
      if (s && (!isFinite(s.x) || !isFinite(s.y) || !isFinite(s.z) ||
          s.x === 0 || s.y === 0 || s.z === 0)) s.set(1, 1, 1);
      if (q && (!isFinite(q.x) || !isFinite(q.y) || !isFinite(q.z) || !isFinite(q.w))) {
        q.set(0, 0, 0, 1);
      }
      if (obj.updateMatrix) obj.updateMatrix();
    });
    model.updateMatrixWorld(true);
  }

  /* ================================================================ */
  /*  Opacity helpers                                                  */
  /* ================================================================ */

  _setModelOpacity(model, opacity, forceOpaque = false) {
    model.traverse(child => {
      if (!child.isMesh && !child.isSkinnedMesh) return;
      const mats = Array.isArray(child.material) ? child.material : [child.material];
      mats.forEach(m => {
        if (!m) return;

        // Pipeline-managed materials (hologram/wireframe) must ALSO fade
        // during the slide transition — otherwise the switch "pops".
        // Preserve their base opacity (e.g. 0.88 hologram / 0.65 wireframe)
        // so the fade target is their authored opacity, not 1.0.
        const base = m._pipelineManaged ? (m.userData?.baseOpacity ?? opacity) : opacity;
        const target = Math.min(base, opacity);

        if (forceOpaque && opacity >= 1 && !m._pipelineManaged) {
          m.transparent = false;
          m.depthWrite = true;
        } else {
          m.transparent = true;
          m.depthWrite = false;
        }
        m.opacity = target;
        m.needsUpdate = true;
      });
    });
  }

  /* ================================================================ */
  /*  Camera — BoundingSphere framing                                  */
  /* ================================================================ */

  _frameCamera(characterId) {
    if (!this.camera || !this.THREE) return;
    const model = this.characterRoots.get(characterId);
    if (!model) return;

    try {
      // Deterministic framing based on the normalized TARGET_HEIGHT.
      // Every model is normalized to the same local height, so the camera
      // distance is CONSTANT — identical viewport size for every character.
      // (The pivot's live scale from hand-tracking is a deliberate user zoom
      //  and does NOT corrupt the per-character framing.)
      const fovRad = (this.camera.fov * Math.PI) / 180;
      // Camera zoom divides the base distance (mouse wheel zoom).
      const zoom = Math.max(0.4, this.cameraZoom || 1);
      const dist   = ((TARGET_HEIGHT / VIEWPORT_FILL) / Math.tan(fovRad / 2)) / zoom;

      this.camera.near = Math.max(0.01, dist * 0.04);
      this.camera.far  = Math.max(100, dist * 8);
      this.camera.updateProjectionMatrix();

      // Model is normalized: feet at y=0, height = TARGET_HEIGHT, centered on X/Z.
      // Look slightly above center so the head is framed comfortably.
      // Pan shifts camera + look target together (middle-mouse pan).
      // Framing nudge: the character sits a little LEFT and a little LOWER on
      // screen (camera looks right-of-center and slightly above the chest).
      const targetY = TARGET_HEIGHT * 0.48;
      const FRAME_SHIFT_X = 0.32; // character appears left of center
      const FRAME_SHIFT_Y = 0.14; // character appears lower in frame
      this._targetCamPos.set(
        this.userPanX + FRAME_SHIFT_X * 0.5,
        targetY * 0.55 + this.userPanY + FRAME_SHIFT_Y * 0.35,
        dist
      );
      this._targetCamLook.set(
        this.userPanX + FRAME_SHIFT_X,
        targetY + this.userPanY * 0.4 + FRAME_SHIFT_Y,
        0
      );

      if (!this._hasCamTarget) {
        this.camera.position.copy(this._targetCamPos);
        this._currentCamLook.copy(this._targetCamLook);
        this.camera.lookAt(this._currentCamLook);
        this._hasCamTarget = true;
      }
    } catch (e) {
      console.warn(`${PREFIX} Camera frame failed:`, e.message);
    }
  }

  /* ================================================================ */
  /*  Material Cache                                                   */
  /* ================================================================ */

  _cacheMaterials(characterId, model) {
    const THREE = this.THREE;
    if (!THREE) return;

    const meshList    = [];
    const origPerMesh = [];

    model.traverse(child => {
      if (!child.isMesh && !child.isSkinnedMesh) return;
      meshList.push(child);
      origPerMesh.push(
        Array.isArray(child.material) ? child.material.slice() : child.material
      );
    });

    this._fixOriginalMaterials(meshList, origPerMesh);

    // Hologram materials — identical pipeline for EVERY character.
    // Pure blue LIGHT look: highly translucent, additive, emissive glow,
    // hologram wireframe grid + scanlines + random glitches (see shader).
    const holoPerMesh = meshList.map(mesh => {
      const holo = new THREE.MeshPhysicalMaterial({
        color:             0x3399ff,
        emissive:          new THREE.Color(0x0055ff),
        emissiveIntensity: 1.2,
        metalness:         0.1,
        roughness:         0.35,
        clearcoat:         0.6,
        clearcoatRoughness: 0.2,
        transparent:       true,
        opacity:           0.42,
        depthWrite:        false,
        side:              THREE.DoubleSide,
        blending:          THREE.AdditiveBlending,
        envMapIntensity:   1.3,
      });
      holo._pipelineManaged = true;
      holo.userData.baseOpacity = 0.45;
      if (mesh.isSkinnedMesh) holo.skinning = true;

      // Animated hologram shader: Fresnel glow, wireframe grid, scanlines,
      // pulse, glitch slice-displacement + RGB split + random flicker
      this._applyHologramShader(holo);
      return holo;
    });

    // Wireframe materials — premium glow, NOT default three.js wireframe.
    const wirePerMesh = meshList.map(mesh => {
      const wire = new THREE.MeshBasicMaterial({
        color:       0x00ffcc,
        wireframe:   true,
        transparent: true,
        opacity:     0.65,
        depthWrite:  false,
        side:        THREE.DoubleSide,
      });
      wire._pipelineManaged = true;
      wire.userData.baseOpacity = 0.65;

      // Animated wireframe shader: moving scanline, emissive bloom, pulse
      this._applyWireframeShader(wire);
      if (mesh.isSkinnedMesh) wire.skinning = true;
      return wire;
    });

    this.materialCache.set(characterId, {
      meshList,
      original:  origPerMesh,
      texture:   origPerMesh,
      hologram:  holoPerMesh,
      wireframe: wirePerMesh,
    });

    console.log(`${PREFIX} Material cache: ${characterId} (${meshList.length} meshes)`);
  }

  /**
   * Hologram shader — translucent BLUE LIGHT hologram with:
   *  - Fresnel edge glow (bright blue rim)
   *  - hologram wireframe grid lines (screen-space, follows the model)
   *  - animated scanlines
   *  - random GLITCHES: horizontal slice displacement (vertex), per-slice
   *    RGB split and random full-body flicker (fragment)
   *  - soft pulse
   * Applied via onBeforeCompile.
   */
  _applyHologramShader(material) {
    const THREE = this.THREE;
    if (!THREE || !material.onBeforeCompile) return;

    material.onBeforeCompile = (shader) => {
      // Store shader reference so updateMaterialUniforms can drive uTime per frame
      material.userData.shader = shader;

      shader.uniforms.uTime = { value: 0 };
      shader.uniforms.uFresnelPower = { value: 2.5 };
      shader.uniforms.uScanIntensity = { value: 0.4 };
      shader.uniforms.uGlitchIntensity = { value: 1.0 };

      shader.vertexShader = `
        uniform float uTime;
        uniform float uGlitchIntensity;
        varying vec3 vNormalW;
        varying vec3 vViewDir;
        varying vec3 vWorldPos;
        varying float vGlitch;
        ${shader.vertexShader}
      `.replace(
        '#include <begin_vertex>',
        `#include <begin_vertex>

        // Hologram glitch — random horizontal slices jump sideways now & then
        float gBand  = floor((transformed.y + 4.0) * 8.0);
        float gRand  = fract(sin(gBand * 127.1 + 311.7) * 43758.5453);
        float gOn    = step(0.86, fract(uTime * 0.9 + gRand * 5.0));
        transformed.x += (gRand - 0.5) * 0.10 * gOn * uGlitchIntensity;
        vGlitch = gOn * gRand;
        `
      ).replace(
        '#include <worldpos_vertex>',
        `#include <worldpos_vertex>
        vNormalW = normalize(mat3(modelMatrix) * normal);
        vViewDir = normalize(cameraPosition - (modelMatrix * vec4(position, 1.0)).xyz);
        vWorldPos = (modelMatrix * vec4(position, 1.0)).xyz;
        `
      );

      shader.fragmentShader = `
        uniform float uTime;
        uniform float uFresnelPower;
        uniform float uScanIntensity;
        uniform float uGlitchIntensity;
        varying vec3 vNormalW;
        varying vec3 vViewDir;
        varying vec3 vWorldPos;
        varying float vGlitch;
        ${shader.fragmentShader}
      `.replace(
        '#include <emissivemap_fragment>',
        `#include <emissivemap_fragment>

        // Fresnel edge glow — bright blue rim
        float fresnel = pow(1.0 - max(dot(normalize(vNormalW), normalize(vViewDir)), 0.0), uFresnelPower);
        totalEmissiveRadiance += vec3(0.15, 0.45, 1.0) * fresnel * 1.3;

        // Hologram wireframe grid — fine blue lines across the surface
        vec3 gridC = abs(fract(vWorldPos * 6.0) - 0.5) / fwidth(vWorldPos * 6.0);
        float gridLine = 1.0 - min(min(gridC.x, gridC.y), gridC.z);
        totalEmissiveRadiance += vec3(0.25, 0.6, 1.0) * gridLine * 0.5;

        // Animated scanlines
        float scanY = fract(vViewDir.y * 18.0 + uTime * 0.6);
        totalEmissiveRadiance += vec3(0.1, 0.5, 1.0) * smoothstep(0.0, 0.08, scanY) * uScanIntensity;

        // Glitch — RGB fringe only (no full-body brightness drop, keeps the view consistent)
        float gFlick = 0.0;
        totalEmissiveRadiance *= (1.0 - 0.5 * gFlick);

        // Glitch — per-slice RGB split (fringe on displaced bands)
        float split = vGlitch * uGlitchIntensity;
        totalEmissiveRadiance.r += split * 0.30;
        totalEmissiveRadiance.b -= split * 0.25;
        totalEmissiveRadiance = max(totalEmissiveRadiance, vec3(0.0));

        // Steady glow — no time-based pulse, keeps brightness consistent
        float pulse = 0.9;
        totalEmissiveRadiance *= pulse;
        `
      );
    };

    // Update time per frame — hook into a shared clock
    material.userData.update = (dt) => {
      if (material.userData._t === undefined) material.userData._t = 0;
      material.userData._t += dt;
      material.userData.forEachUniform = (u) => { if (u) u.value = material.userData._t; };
    };
  }

  /**
   * Wireframe shader — cyan glowing lines, moving scanline, emissive bloom.
   */
  _applyWireframeShader(material) {
    const THREE = this.THREE;
    if (!THREE || !material.onBeforeCompile) return;

    material.onBeforeCompile = (shader) => {
      // Store shader reference so updateMaterialUniforms can drive uTime per frame
      material.userData.shader = shader;

      shader.uniforms.uTime = { value: 0 };
      shader.uniforms.uScan = { value: 0.5 };

      shader.vertexShader = `
        varying vec3 vPos;
        ${shader.vertexShader}
      `.replace(
        '#include <begin_vertex>',
        `#include <begin_vertex>
        vPos = transformed;
        `
      );

      shader.fragmentShader = `
        uniform float uTime;
        uniform float uScan;
        varying vec3 vPos;
        ${shader.fragmentShader}
      `.replace(
        '#include <color_fragment>',
        `#include <color_fragment>

        // Moving scanline sweep along Y
        float scanPos = fract(vPos.y * 2.0 - uTime * 0.5);
        vec3 scanColor = vec3(0.0, 1.0, 0.8) * (0.4 + 0.6 * smoothstep(0.0, 0.15, scanPos) * (1.0 - smoothstep(0.85, 1.0, scanPos)));
        diffuseColor.rgb += scanColor;

        // Pulse glow (steady — consistent brightness)
        float pulse = 0.85;
        diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.0, 1.0, 0.85), 0.35);
        diffuseColor.rgb *= pulse;
        `
      );
    };
  }

  /**
   * Animate all pipeline-managed materials (hologram/wireframe uniforms).
   * Called every frame from the animate loop.
   */
  updateMaterialUniforms(dt) {
    this.materialCache.forEach(cache => {
      [...cache.hologram, ...cache.wireframe].forEach(m => {
        if (!m || !m.onBeforeCompile) return;
        if (m.userData._t === undefined) m.userData._t = 0;
        m.userData._t += dt || 0;
        // Update the compiled shader uniforms (shader ref stored in onBeforeCompile)
        if (m.userData.shader && m.userData.shader.uniforms) {
          if (m.userData.shader.uniforms.uTime) m.userData.shader.uniforms.uTime.value = m.userData._t;
        }
        m.needsUpdate = false;
      });
    });
  }

  _fixOriginalMaterials(meshList, origPerMesh) {
    const THREE = this.THREE;
    if (!THREE) return;

    const maxAnisotropy = (this.renderer?.capabilities?.getMaxAnisotropy?.()) || 8;

    meshList.forEach((mesh, i) => {
      const mats = Array.isArray(origPerMesh[i]) ? origPerMesh[i] : [origPerMesh[i]];
      mats.forEach(m => {
        if (!m) return;
        // Never re-touch pipeline-managed materials (hologram/wireframe) — we author them.
        if (m._pipelineManaged) return;

        // ---- Identical texture pipeline for EVERY imported material ----
        const setMap = (map, cs) => {
          if (!map) return;
          map.colorSpace = cs;
          map.needsUpdate = true;
          map.generateMipmaps = true;
          map.minFilter = THREE.LinearMipmapLinearFilter;
          map.magFilter = THREE.LinearFilter;
          map.flipY = false;
          if (maxAnisotropy > 1) map.anisotropy = maxAnisotropy;
        };
        setMap(m.map,           THREE.SRGBColorSpace);
        setMap(m.emissiveMap,   THREE.SRGBColorSpace);
        setMap(m.normalMap,     THREE.LinearSRGBColorSpace);
        setMap(m.roughnessMap,  THREE.LinearSRGBColorSpace);
        setMap(m.metalnessMap,  THREE.LinearSRGBColorSpace);
        setMap(m.aoMap,         THREE.LinearSRGBColorSpace);
        setMap(m.alphaMap,      THREE.LinearSRGBColorSpace);
        setMap(m.bumpMap,       THREE.LinearSRGBColorSpace);
        setMap(m.displacementMap, THREE.LinearSRGBColorSpace);
        setMap(m.specularMap,   THREE.LinearSRGBColorSpace);

        // ---- Metalness / roughness normalization (Standard & Physical) ----
        // Remove "crushed black" imports by lifting near-zero metalness and
        // clamping muddy roughness so every character responds to light identically.
        if ('metalness' in m && typeof m.metalness === 'number' && m.metalness < 0.05) {
          m.metalness = 0.15;
        }
        if ('roughness' in m && typeof m.roughness === 'number' && m.roughness > 0.92) {
          m.roughness = 0.85;
        }
        // Normal map intensity — boost weak normal maps so surface detail pops.
        if ('normalScale' in m && m.normalScale) {
          const s = m.normalScale.x || 1;
          if (s < 0.4)      m.normalScale.set(0.7, 0.7);
          else if (s > 2.5) m.normalScale.set(1.2, 1.2);
        }
        // Physical materials — premium clearcoat + specular for AAA metal response.
        if (m.isMeshPhysicalMaterial) {
          if (typeof m.clearcoat !== 'number' || m.clearcoat < 0.3) m.clearcoat = 0.5;
          if (typeof m.clearcoatRoughness !== 'number') m.clearcoatRoughness = 0.35;
          if (typeof m.specularIntensity === 'number' && m.specularIntensity < 0.5) {
            m.specularIntensity = 0.8;
          }
        }
        // Phong / Lambert — brighter specular response for clean highlights.
        if (m.isMeshPhongMaterial) {
          if (!m.specular) m.specular = new THREE.Color(0x444444);
          m.shininess = Math.max(m.shininess || 30, 45);
        }
        // Lambert — same premium response (no specular, just brightness lift).

        // Environment reflections — every material, same intensity.
        m.envMapIntensity = Math.max(m.envMapIntensity || 1, 1.4);

        // Emissive — lift faint emissives so glowing parts stay readable.
        if ('emissive' in m && m.emissive) {
          const e = m.emissive;
          const elum = 0.2126 * e.r + 0.7152 * e.g + 0.0722 * e.b;
          if (elum > 0.001 && (typeof m.emissiveIntensity !== 'number' || m.emissiveIntensity < 0.2)) {
            m.emissiveIntensity = 0.5;
          }
        }

        // Ensure opaque unless the material explicitly uses transparency / alpha maps
        if (!m.alphaMap && !(m.alphaTest > 0) && (m.opacity >= 0.99 || m.opacity === undefined)) {
          m.transparent = false;
          m.opacity     = 1.0;
        }
        m.depthWrite  = true;

        // ---- Brightness equalization (fixes Spider-Man / Iron Man dark patches) ----
        // Textured materials: lift base color luminance floor so crushed blacks are repaired.
        // Untextured materials: enforce a higher floor so no flat-black imports remain.
        if (m.color) {
          const baseLum = 0.2126 * m.color.r + 0.7152 * m.color.g + 0.0722 * m.color.b;
          const floor = m.map ? 0.08 : 0.22;
          if (baseLum < floor) {
            const scale = floor / Math.max(baseLum, 0.001);
            m.color.r = Math.min(1, m.color.r * scale);
            m.color.g = Math.min(1, m.color.g * scale);
            m.color.b = Math.min(1, m.color.b * scale);
          }
        }

        m.needsUpdate = true;
      });
    });
  }

  _applyMode(characterId, mode) {
    const cache = this.materialCache.get(characterId);
    if (!cache) return;

    const targetMats = this._getMaterialsForMode(cache, mode);
    cache.meshList.forEach((mesh, i) => {
      if (targetMats && targetMats[i]) {
        mesh.material = targetMats[i];
      }
    });
  }

  /* ================================================================ */
  /*  Lighting — Tony Stark's Lab, blue hologram theme                 */
  /* ================================================================ */

  _setupLighting(mode) {
    if (!this.scene || !this.THREE) return;
    const THREE = this.THREE;

    this._lights.forEach(l => this.scene.remove(l));
    this._lights = [];

    const add = l => { this.scene.add(l); this._lights.push(l); return l; };

    // Blue hologram theme — strong blue rim, fill, ambient, energy atmosphere.
    // Texture mode restores neutral studio so original textures are exact.

    // Shared premium base (both modes get rich reflections)
    const hemi = new THREE.HemisphereLight(
      mode === RENDER_MODE.TEXTURE ? 0x87ceeb : 0x1144aa,
      mode === RENDER_MODE.TEXTURE ? 0x443822 : 0x001122,
      mode === RENDER_MODE.TEXTURE ? 1.15 : 1.15
    );
    add(hemi);

    // Ambient — lifted so no character has crushed shadows
    const ambient = new THREE.AmbientLight(
      mode === RENDER_MODE.TEXTURE ? 0xfff5e0 : 0x113366,
      mode === RENDER_MODE.TEXTURE ? 1.25 : 2.2
    );
    add(ambient);

    // Key light — cinematic, brighter highlights
    const key = new THREE.DirectionalLight(
      mode === RENDER_MODE.TEXTURE ? 0xfff8e7 : 0x88ccff,
      mode === RENDER_MODE.TEXTURE ? 4.4 : 4.2
    );
    key.position.set(4, 7, 5);
    key.castShadow = mode === RENDER_MODE.TEXTURE;
    if (key.shadow) {
      key.shadow.mapSize.set(2048, 2048);
      key.shadow.bias = -0.0004;
      key.shadow.normalBias = 0.02;
      key.shadow.radius = 4;
    }
    add(key);

    // Fill (cool blue) — softer but stronger to keep metals alive on the shadow side
    const fill = new THREE.DirectionalLight(
      mode === RENDER_MODE.TEXTURE ? 0xd0e8ff : 0x4499ff,
      mode === RENDER_MODE.TEXTURE ? 1.7 : 2.6
    );
    fill.position.set(-5, 3, 2);
    add(fill);

    // Back rim (strong blue in hologram mode) — premium edge separation
    const rim = new THREE.DirectionalLight(
      mode === RENDER_MODE.TEXTURE ? 0xffffff : 0x00aaff,
      mode === RENDER_MODE.TEXTURE ? 1.35 : 2.7
    );
    rim.position.set(0, 5, -6);
    add(rim);

    // Warm accent — adds cinematic specular pop to metallic surfaces
    const accent = new THREE.DirectionalLight(
      mode === RENDER_MODE.TEXTURE ? 0xffcc88 : 0x88ccff,
      mode === RENDER_MODE.TEXTURE ? 0.7 : 0.7
    );
    accent.position.set(-3, 4, 4);
    add(accent);

    // Blue under-glow in hologram mode (energy atmosphere)
    if (mode !== RENDER_MODE.TEXTURE) {
      // Wide radius so the glow reaches the whole figure, not just the feet
      const under = new THREE.PointLight(0x0088ff, 10, 18);
      under.position.set(0, -1.2, 0);
      add(under);

      const rightFill = new THREE.DirectionalLight(0x00ccff, 1.3);
      rightFill.position.set(6, 2, 3);
      add(rightFill);
    }

    // Environment reflection intensity
    if (this.scene.environment) {
      this.scene.environmentIntensity = mode === RENDER_MODE.TEXTURE ? 1.2 : 0.7;
    }

    // PMREM environment — set up once, used by all modes.
    // Uses the explicitly imported RoomEnvironment (NOT THREE.RoomEnvironment,
    // which does not exist in three.module.js — this was the root cause of
    // "RoomEnvironment is not defined" and dark/black metallic materials).
    if (!this._envSetup) {
      this._envSetup = true;
      try {
        if (THREE.PMREMGenerator && RoomEnvironment) {
          const pmrem = new THREE.PMREMGenerator(this.renderer);
          const env   = new RoomEnvironment();
          // Three.js 0.160+: fromScene accepts a scene and optional render target.
          const rt    = pmrem.fromScene(env);
          this.scene.environment = rt.texture;
          this.scene.environmentIntensity = mode === RENDER_MODE.TEXTURE ? 1.2 : 0.7;
          pmrem.dispose();
          console.log(`${PREFIX} PMREM environment created`);
        }
      } catch (e) {
        console.warn(`${PREFIX} PMREM unavailable:`, e.message);
      }
    }
  }

  /* ================================================================ */
  /*  Hologram projection light (beam from the floor, no base)          */
  /* ================================================================ */

  /**
   * Build the hologram light cone: a soft volumetric-looking beam rising
   * from the floor beneath the character's feet (classic projector look).
   * Pure light — no base / pedestal mesh. Visible only in HOLOGRAM mode.
   *
   * Two nested cones (outer soft beam + inner hot core) with an animated
   * additive shader: vertical falloff, radial softness, rising projector
   * bands and a subtle power flicker.
   */
  _createHologramLight() {
    // Beam light intentionally disabled — removed per request (clean look).
    return;
    const THREE = this.THREE;
    if (!THREE || !this.scene) return;

    const BEAM_HEIGHT    = 3.3;   // world units above the floor (char is 2.2)
    const BEAM_TOP_R     = 0.9;   // wide halo — fully covers the figure
    const BEAM_BOTTOM_R  = 0.55;  // generous origin at the feet
    const FLOOR_Y        = -0.5;  // pivot / character feet level (set in HTML)

    // Open-ended cone (no caps — a light beam, not a solid object)
    const geo = new THREE.CylinderGeometry(
      BEAM_TOP_R, BEAM_BOTTOM_R, BEAM_HEIGHT, 48, 24, true
    );

    const makeBeamMaterial = (baseOpacity) => {
      const mat = new THREE.ShaderMaterial({
        transparent: true,
        depthWrite:  false,
        depthTest:   true,
        side:        THREE.DoubleSide,
        blending:    THREE.AdditiveBlending,
        uniforms: {
          uTime:      { value: 0 },
          uColor:     { value: new THREE.Color(0x1a4dff) },   // deep hologram blue (reference look)
          uCoreColor: { value: new THREE.Color(0x66aaff) },   // blue light at the base
          uOpacity:   { value: baseOpacity },
        },
        vertexShader: `
          varying vec3 vWorldPos;
          varying float vH;
          void main() {
            vec4 wp = modelMatrix * vec4(position, 1.0);
            vWorldPos = wp.xyz;
            // 0 = beam base (floor), 1 = beam top — geometry-local, scale-invariant
            vH = (position.y + ${BEAM_HEIGHT / 2}) / ${BEAM_HEIGHT};
            gl_Position = projectionMatrix * viewMatrix * wp;
          }
        `,
        fragmentShader: `
          uniform float uTime;
          uniform vec3 uColor;
          uniform vec3 uCoreColor;
          uniform float uOpacity;
          varying vec3 vWorldPos;
          varying float vH;

          void main() {
            // Vertical fade — brightest at the floor, dissolves near the top
            float fadeY = 1.0 - smoothstep(0.0, 0.9, vH);

            // Radial softness — denser near the beam axis (fake volumetric)
            float r = length(vWorldPos.xz);
            float radial = 1.0 - smoothstep(0.15, 1.35, r);

            // Projector bands drifting up the beam
            float bandPhase = vH * 7.0 - uTime * 0.8;
            float bands = 0.5 + 0.5 * sin(bandPhase * 6.2831853);
            bands = 0.35 + 0.65 * pow(bands, 2.0);

            // Steady power (no flicker — consistent brightness)
            float flick = 1.0;

            // Color: brighter blue at the floor → deep blue toward the top
            vec3 col = mix(uCoreColor, uColor, smoothstep(0.0, 0.6, vH));
            col *= 0.55 + 0.45 * bands;

            float alpha = fadeY * radial * (0.45 + 0.55 * bands) * flick * uOpacity;

            gl_FragColor = vec4(col, alpha);
            #include <tonemapping_fragment>
            #include <colorspace_fragment>
          }
        `,
      });
      mat.userData.baseOpacity = baseOpacity;
      return mat;
    };

    const group = new THREE.Group();
    group.position.set(0, FLOOR_Y, 0); // planted at the character's feet

    // Outer soft beam
    const beam = new THREE.Mesh(geo, makeBeamMaterial(0.5));
    beam.position.y = BEAM_HEIGHT / 2;
    group.add(beam);

    // Inner hot core — narrower, brighter, sells the projector look
    const core = new THREE.Mesh(geo, makeBeamMaterial(0.42));
    core.position.y = BEAM_HEIGHT / 2;
    core.scale.set(0.55, 1, 0.55);
    group.add(core);

    group.visible = this.mode === RENDER_MODE.HOLOGRAM;
    this.scene.add(group);
    this._holoLight = group;

    console.log(`${PREFIX} Hologram light cone created (beam only, no base)`);
  }

  /**
   * Drive the beam's opacity (used by the mode cross-fade).
   * @param {number} factor 0..1 — multiplied by each material's base opacity.
   */
  _setHoloLightOpacity(factor) {
    if (!this._holoLight) return;
    const f = Math.max(0, Math.min(1, factor));
    this._holoLight.traverse(obj => {
      if (!obj.isMesh || !obj.material || !obj.material.uniforms) return;
      const base = obj.material.userData?.baseOpacity ?? 0.55;
      if (obj.material.uniforms.uOpacity) {
        obj.material.uniforms.uOpacity.value = base * f;
      }
    });
  }

  /* ================================================================ */
  /*  Cleanup                                                          */
  /* ================================================================ */

  _disposeCache(characterId) {
    const cache = this.materialCache.get(characterId);
    if (!cache) return;
    [...cache.hologram, ...cache.wireframe].forEach(m => {
      try { m.dispose(); } catch (_) {}
    });
    this.materialCache.delete(characterId);
  }

  dispose() {
    this.materialCache.forEach((cache, id) => this._disposeCache(id));
    this.materialCache.clear();
    this.characterRoots.clear();
    this._lights.forEach(l => this.scene.remove(l));
    this._lights = [];
    if (this._holoLight) {
      this.scene.remove(this._holoLight);
      this._holoLight.traverse(obj => {
        if (obj.geometry) try { obj.geometry.dispose(); } catch (_) {}
        if (obj.material) try { obj.material.dispose(); } catch (_) {}
      });
      this._holoLight = null;
    }
  }
}

let _instance = null;
export function getRenderingPipeline() { return _instance; }
export function initRenderingPipeline({ scene, camera, renderer, pivot, THREE }) {
  if (!_instance) {
    _instance = new RenderingPipeline({ scene, camera, renderer, pivot, THREE });
  }
  return _instance;
}
