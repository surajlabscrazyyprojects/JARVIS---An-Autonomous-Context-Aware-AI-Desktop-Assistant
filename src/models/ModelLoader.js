/**
 * Model Loader
 * Handles GLTF loading, centering, caching, and disposal.
 * Does NOT set transparent=true globally — that is handled by CharacterIntegration fade system.
 */

export class ModelLoader {
    constructor(gltfLoaderInstance, THREE_ref) {
        this.gltfLoader = gltfLoaderInstance;
        this.THREE = THREE_ref || (typeof window !== 'undefined' ? window.THREE : null);
        this.cache = new Map();           // characterId → original model
        this.clipCache = new Map();       // characterId → AnimationClip[]
        this.loadingPromises = new Map(); // characterId → Promise

        if (!this.THREE) {
            console.warn('[ModelLoader] THREE reference missing — centering disabled');
        }
    }

    /**
     * Load model. Returns the ORIGINAL (not a clone) so CharacterIntegration
     * can attach it directly. Subsequent calls return a fresh clone.
     */
    async loadModel(profile, options = {}) {
        const characterId = profile.id;

        // Support both centralized (modelPath) and legacy (model.path) structures
        const modelPath = profile.modelPath || profile.model?.path;
        if (!modelPath) {
            throw new Error(`[ModelLoader] No model path for ${characterId}`);
        }

        console.log(`[ModelLoader] Resolving: ${characterId} → ${modelPath}`);

        // Return clone of cached model
        if (this.cache.has(characterId)) {
            console.log(`[ModelLoader] Cache HIT: ${characterId}`);
            const cached = this.cache.get(characterId);
            const cloned = this._cloneWithAnimations(cached, characterId);
            return cloned;
        }

        // Debounce duplicate loads
        if (this.loadingPromises.has(characterId)) {
            console.log(`[ModelLoader] Already loading: ${characterId}`);
            const original = await this.loadingPromises.get(characterId);
            return this._cloneWithAnimations(original, characterId);
        }

        const loadPromise = this._performLoad(profile, options);
        this.loadingPromises.set(characterId, loadPromise);

        try {
            const model = await loadPromise;
            this.cache.set(characterId, model);
            console.log(`[ModelLoader] Cached: ${characterId}`);
            // Return a clone so the cache stays clean
            return this._cloneWithAnimations(model, characterId);
        } catch (err) {
            console.error(`[ModelLoader] Failed: ${characterId}`, err);
            throw err;
        } finally {
            this.loadingPromises.delete(characterId);
        }
    }

    /**
     * Clone a model and re-attach animation clips from the clip cache.
     *
     * ROOT CAUSE FIX: THREE.Object3D.clone(true) does NOT deep-clone
     * SkinnedMesh skeletons — the cloned meshes keep references to the
     * ORIGINAL skeleton's bones, which corrupts vertex binding and makes
     * the model invisible (e.g. Thanos/Batman). The correct approach is
     * THREE.SkeletonUtils.clone(), which clones the full skeleton graph.
     *
     * We also re-attach animation clips from the separate clip cache so
     * AnimationMixer works correctly after cloning.
     */
    _cloneWithAnimations(original, characterId) {
        // Prefer SkeletonUtils.clone() — required for correct SkinnedMesh
        // skeleton cloning. Try multiple sources for robustness.
        const SkeletonUtils = this._getSkeletonUtils();
        let cloned;
        if (SkeletonUtils && typeof SkeletonUtils.clone === 'function') {
            cloned = SkeletonUtils.clone(original);
        } else {
            console.warn(
                '[ModelLoader] SkeletonUtils not available — falling back to ' +
                'Object3D.clone(true). Skinned meshes may not render correctly.'
            );
            cloned = original.clone(true);
        }

        // Re-attach clips from cache (not from the cloned userData which may be stale)
        const clips = this.clipCache.get(characterId) || original.userData?.animations || [];
        cloned.userData.animations = clips;
        cloned.userData.characterId = characterId;

        return cloned;
    }

    /**
     * Resolve THREE.SkeletonUtils from available sources.
     * Checks module import, THREE global, and window global.
     */
    _getSkeletonUtils() {
        if (this._skeletonUtils) return this._skeletonUtils;
        const THREE = this.THREE;
        const candidates = [
            THREE?.SkeletonUtils,
            typeof window !== 'undefined' ? window.THREE?.SkeletonUtils : null,
            typeof window !== 'undefined' ? window.SkeletonUtils : null,
        ];
        this._skeletonUtils = candidates.find(s => s && typeof s.clone === 'function') || null;
        return this._skeletonUtils;
    }

    _performLoad(profile, options) {
        return new Promise((resolve, reject) => {
            const path = profile.modelPath || profile.model?.path;
            const defaultPosition = profile.defaultPosition || profile.model?.defaultPosition || {};
            const characterId = profile.id;

            console.log(`[ModelLoader] GLTFLoader.load: ${characterId}`);

            this.gltfLoader.load(
                path,
                gltf => {
                    try {
                        const scene = gltf.scene;

                        // Count meshes for diagnostics
                        let meshCount = 0;
                        scene.traverse(c => { if (c.isMesh || c.isSkinnedMesh) meshCount++; });
                        console.log(`[ModelLoader] Parsed: ${characterId} — ${meshCount} meshes, ${gltf.animations?.length || 0} animations`);

                        // Store clips in separate cache (survives cloning)
                        if (gltf.animations && gltf.animations.length > 0) {
                            this.clipCache.set(characterId, gltf.animations);
                            scene.userData.animations = gltf.animations;
                        }

                        scene.userData.characterId = characterId;
                        scene.userData.loadedAt = Date.now();

                        // Fix texture color spaces BEFORE centering
                        this._fixTextureColorSpaces(scene);

                        // Pre-warm GPU textures to eliminate pop-in stutter
                        this._prewarmModel(scene);

                        // Center model (scale is handled by CharacterIntegration._normalizeModelScale)
                        this._centerModel(scene, profile);

                        console.log(`[ModelLoader] ✓ Loaded: ${characterId}`);
                        options.onProgress && options.onProgress(100);
                        resolve(scene);
                    } catch (err) {
                        console.error(`[ModelLoader] Process error ${characterId}:`, err);
                        reject(err instanceof Error ? err : new Error(String(err)));
                    }
                },
                xhr => {
                    if (xhr.total > 0) {
                        const pct = Math.round((xhr.loaded / xhr.total) * 100);
                        options.onProgress && options.onProgress(pct);
                    }
                },
                err => {
                    const msg = `Failed to load "${characterId}" from "${path}": ${err?.message || String(err)}`;
                    console.error(`[ModelLoader] ✗ ${msg}`);
                    const wrapped = new Error(msg);
                    reject(wrapped);
                    options.onError && options.onError(wrapped);
                }
            );
        });
    }

    /**
     * Fix texture color spaces so they render correctly with SRGBColorSpace renderer.
     * Also configures anisotropic filtering and mipmapping for high-resolution clarity.
     */
    _fixTextureColorSpaces(scene) {
        if (!this.THREE) return;
        const THREE = this.THREE;
        let fixed = 0;
        const maxAnisotropy = (typeof window !== 'undefined' && window.__renderer) ?
            (window.__renderer.capabilities?.getMaxAnisotropy() || 8) : 8;

        scene.traverse(child => {
            if (!child.isMesh && !child.isSkinnedMesh) return;
            const mats = Array.isArray(child.material) ? child.material : [child.material];
            mats.forEach(m => {
                if (!m) return;
                const setMapCS = (map, cs) => {
                    if (map && map.colorSpace !== cs) {
                        map.colorSpace = cs;
                        map.needsUpdate = true;
                        fixed++;
                    }
                };

                // Base color & emissive maps must be sRGB
                setMapCS(m.map, THREE.SRGBColorSpace);
                setMapCS(m.emissiveMap, THREE.SRGBColorSpace);

                // Data maps (normal, roughness, metalness, AO, alpha, bump) must be Linear
                setMapCS(m.normalMap, THREE.LinearSRGBColorSpace);
                setMapCS(m.roughnessMap, THREE.LinearSRGBColorSpace);
                setMapCS(m.metalnessMap, THREE.LinearSRGBColorSpace);
                setMapCS(m.aoMap, THREE.LinearSRGBColorSpace);
                setMapCS(m.alphaMap, THREE.LinearSRGBColorSpace);
                setMapCS(m.bumpMap, THREE.LinearSRGBColorSpace);
                setMapCS(m.displacementMap, THREE.LinearSRGBColorSpace);

                // Configure anisotropic filtering & mipmapping for crisp textures
                ['map', 'emissiveMap', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'alphaMap', 'bumpMap'].forEach(key => {
                    const tex = m[key];
                    if (tex) {
                        tex.flipY = false;
                        tex.generateMipmaps = true;
                        tex.minFilter = THREE.LinearMipmapLinearFilter;
                        tex.magFilter = THREE.LinearFilter;
                        if (maxAnisotropy > 1) {
                            tex.anisotropy = maxAnisotropy;
                        }
                    }
                });

                m.needsUpdate = true;
            });
        });

        if (fixed > 0) console.log(`[ModelLoader] Color spaces fixed: ${fixed} textures`);
    }

    /**
     * Pre-warm GPU textures to eliminate pop-in micro-stutter when model is attached.
     */
    _prewarmModel(scene) {
        const renderer = typeof window !== 'undefined' ? window.__renderer : null;
        if (!renderer || typeof renderer.initTexture !== 'function') return;

        scene.traverse(child => {
            if (!child.isMesh && !child.isSkinnedMesh) return;
            const mats = Array.isArray(child.material) ? child.material : [child.material];
            mats.forEach(m => {
                if (!m) return;
                ['map', 'emissiveMap', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'alphaMap', 'bumpMap'].forEach(key => {
                    if (m[key]) {
                        try { renderer.initTexture(m[key]); } catch (_) {}
                    }
                });
            });
        });
    }

    /**
     * Center model on bounding box. Scale is applied by CharacterIntegration.
     */
    _centerModel(scene, profile) {
        if (!this.THREE) return;
        const THREE = this.THREE;

        try {
            const box = new THREE.Box3().setFromObject(scene);
            if (!isFinite(box.min.x) || !isFinite(box.max.x)) {
                console.warn('[ModelLoader] Invalid bounding box, skipping center');
                return;
            }

            const center = box.getCenter(new THREE.Vector3());
            const size   = box.getSize(new THREE.Vector3());

            // Support both centralized (defaultPosition) and legacy (model.defaultPosition) structures
            const defaultPosition = profile?.defaultPosition || profile?.model?.defaultPosition || {};

            scene.position.set(
                -center.x + (defaultPosition.x || 0),
                -box.min.y + (defaultPosition.y || 0),
                -center.z + (defaultPosition.z || 0)
            );

            console.log(`[ModelLoader] Centered: ${size.x.toFixed(2)}×${size.y.toFixed(2)}×${size.z.toFixed(2)}`);
        } catch (e) {
            console.error('[ModelLoader] _centerModel error:', e);
        }
    }

    disposeModel(model) {
        if (!model) return;
        let geoms = 0, mats = 0, texs = 0;

        model.traverse(child => {
            if (child.userData?.animationMixer) {
                try { child.userData.animationMixer.stopAllAction(); } catch (_) {}
                child.userData.animationMixer = null;
            }
            if (child.geometry) {
                try { child.geometry.dispose(); geoms++; } catch (_) {}
            }
            if (child.material) {
                const arr = Array.isArray(child.material) ? child.material : [child.material];
                arr.forEach(m => {
                    if (!m) return;
                    try {
                        ['map','normalMap','emissiveMap','roughnessMap','metalnessMap','aoMap','specularMap','bumpMap'].forEach(k => {
                            if (m[k]) { m[k].dispose(); texs++; }
                        });
                        m.dispose(); mats++;
                    } catch (_) {}
                });
            }
        });

        console.log(`[ModelLoader] Disposed: geoms=${geoms} mats=${mats} texs=${texs}`);
    }

    removeFromCache(characterId) {
        if (this.cache.has(characterId)) {
            this.disposeModel(this.cache.get(characterId));
            this.cache.delete(characterId);
            this.clipCache.delete(characterId);
        }
    }

    clearCache() {
        this.cache.forEach(m => this.disposeModel(m));
        this.cache.clear();
        this.clipCache.clear();
        this.loadingPromises.clear();
    }

    getCacheStats() {
        return { size: this.cache.size, characterIds: Array.from(this.cache.keys()) };
    }
}
