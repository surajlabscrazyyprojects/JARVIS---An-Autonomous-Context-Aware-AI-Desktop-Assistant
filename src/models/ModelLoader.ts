/**
 * Model Loader
 * Handles glTF model loading, material overrides, disposal, and caching
 * Prevents VRAM leaks through proper resource cleanup
 */

import type * as THREE from 'three';
import type { CharacterModel, CharacterProfile } from '../types/Character.js';

export interface LoaderOptions {
  onProgress?: (progress: number) => void;
  onError?: (error: Error) => void;
}

export class ModelLoader {
  private gltfLoader: any; // GLTFLoader from Three.js
  private textureLoader: any; // TextureLoader
  private cache: Map<string, THREE.Group> = new Map();
  private loadingPromises: Map<string, Promise<THREE.Group>> = new Map();

  constructor(gltfLoaderInstance: any, textureLoaderInstance?: any) {
    this.gltfLoader = gltfLoaderInstance;
    this.textureLoader = textureLoaderInstance;
  }

  /**
   * Load a character model from path
   * Uses caching to prevent duplicate loads
   */
  async loadModel(
    profile: CharacterProfile,
    options?: LoaderOptions
  ): Promise<THREE.Group> {
    const characterId = profile.id;
    const modelPath = profile.model.path;

    // Return cached model if available
    if (this.cache.has(characterId)) {
      const cached = this.cache.get(characterId);
      if (cached) {
        console.log(`✓ Using cached model: ${characterId}`);
        return cached.clone(); // Clone to avoid state conflicts
      }
    }

    // Return existing loading promise if model is already loading
    if (this.loadingPromises.has(characterId)) {
      console.log(`⏳ Model already loading: ${characterId}, returning existing promise`);
      return this.loadingPromises.get(characterId)!;
    }

    // Create and cache loading promise
    const loadPromise = this._performLoad(profile, options);
    this.loadingPromises.set(characterId, loadPromise);

    try {
      const model = await loadPromise;
      this.cache.set(characterId, model);
      return model.clone();
    } finally {
      this.loadingPromises.delete(characterId);
    }
  }

  /**
   * Internal load implementation
   */
  private async _performLoad(
    profile: CharacterProfile,
    options?: LoaderOptions
  ): Promise<THREE.Group> {
    return new Promise((resolve, reject) => {
      const modelPath = profile.model.path;
      const characterId = profile.id;

      console.log(`🔄 Loading model: ${characterId} from ${modelPath}`);

      this.gltfLoader.load(
        modelPath,
        (gltf: any) => {
          try {
            const scene = gltf.scene;

            // Apply character-specific material overrides
            if (profile.model.materialOverride) {
              this._applyMaterialOverrides(scene, profile.model.materialOverride);
            }

            // Fix texture color spaces BEFORE centering
            this._fixTextureColorSpaces(scene);

            // Pre-warm GPU textures to eliminate pop-in micro-stutter
            this._prewarmModel(scene);

            // Center and position model
            this._centerModel(scene, profile.model);

            // Apply animations if available
            if (gltf.animations && gltf.animations.length > 0) {
              (scene as any).animations = gltf.animations;
            }

            console.log(`✓ Model loaded successfully: ${characterId}`);
            resolve(scene);
          } catch (error) {
            const err = error instanceof Error ? error : new Error(String(error));
            console.error(`✗ Error processing model: ${characterId}`, err);
            reject(err);
            options?.onError?.(err);
          }
        },
        (progress: any) => {
          const percentComplete = (progress.loaded / progress.total) * 100;
          options?.onProgress?.(percentComplete);
        },
        (error: any) => {
          const err = error instanceof Error ? error : new Error(String(error));
          console.error(`✗ Model load failed: ${characterId}`, err);
          reject(err);
          options?.onError?.(err);
        }
      );
    });
  }

  /**
   * Apply material overrides to all meshes in model
   */
  private _applyMaterialOverrides(
    scene: THREE.Group,
    override: CharacterModel['materialOverride']
  ): void {
    if (!override) return;

    scene.traverse((child: any) => {
      if (child.isMesh && child.material) {
        // Material override will be applied using THREE exported globally
        // in the HTML template via the importmap
        const THREE = (window as any).THREE;
        const material = new THREE.MeshStandardMaterial({
          color: override.color,
          emissive: override.emissive,
          emissiveIntensity: override.emissiveIntensity,
          transparent: true,
          opacity: override.opacity,
          blending: THREE.AdditiveBlending,
        });
        child.material = material;
      }
    });
  }

  /**
   * Fix texture color spaces so they render correctly with SRGBColorSpace renderer
   */
  private _fixTextureColorSpaces(scene: THREE.Group): void {
    const THREE = (window as any).THREE;
    if (!THREE) return;

    const maxAnisotropy = (window as any).__renderer?.capabilities?.getMaxAnisotropy() || 8;

    scene.traverse((child: any) => {
      if (!child.isMesh && !child.isSkinnedMesh) return;
      const mats = Array.isArray(child.material) ? child.material : [child.material];
      mats.forEach((m: any) => {
        if (!m) return;
        const setMapCS = (map: any, cs: any) => {
          if (map && map.colorSpace !== cs) {
            map.colorSpace = cs;
            map.needsUpdate = true;
          }
        };

        setMapCS(m.map, THREE.SRGBColorSpace);
        setMapCS(m.emissiveMap, THREE.SRGBColorSpace);

        setMapCS(m.normalMap, THREE.LinearSRGBColorSpace);
        setMapCS(m.roughnessMap, THREE.LinearSRGBColorSpace);
        setMapCS(m.metalnessMap, THREE.LinearSRGBColorSpace);
        setMapCS(m.aoMap, THREE.LinearSRGBColorSpace);
        setMapCS(m.alphaMap, THREE.LinearSRGBColorSpace);
        setMapCS(m.bumpMap, THREE.LinearSRGBColorSpace);
        setMapCS(m.displacementMap, THREE.LinearSRGBColorSpace);

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
  }

  /**
   * Pre-warm GPU textures to eliminate pop-in micro-stutter
   */
  private _prewarmModel(scene: THREE.Group): void {
    const renderer = (window as any).__renderer;
    if (!renderer || typeof renderer.initTexture !== 'function') return;

    scene.traverse((child: any) => {
      if (!child.isMesh && !child.isSkinnedMesh) return;
      const mats = Array.isArray(child.material) ? child.material : [child.material];
      mats.forEach((m: any) => {
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
   * Center model in scene based on bounding box
   */
  private _centerModel(scene: THREE.Group, modelConfig: CharacterModel): void {
    const THREE = (window as any).THREE;
    const box = new THREE.Box3().setFromObject(scene);
    const center = box.getCenter(new THREE.Vector3());

    scene.position.set(
      -center.x + modelConfig.defaultPosition.x,
      -box.min.y + modelConfig.defaultPosition.y,
      -center.z + modelConfig.defaultPosition.z
    );

    scene.scale.set(modelConfig.scale, modelConfig.scale, modelConfig.scale);
  }

  /**
   * Properly dispose of model to prevent VRAM leaks
   */
  disposeModel(model: THREE.Group | null): void {
    if (!model) return;

    model.traverse((child: any) => {
      // Dispose geometry
      if (child.geometry) {
        child.geometry.dispose();
      }

      // Dispose materials
      if (child.material) {
        if (Array.isArray(child.material)) {
          child.material.forEach((m: any) => m.dispose?.());
        } else {
          child.material.dispose?.();
        }
      }

      // Dispose textures
      if (child.material?.map) child.material.map.dispose();
      if (child.material?.normalMap) child.material.normalMap.dispose();
      if (child.material?.roughnessMap) child.material.roughnessMap.dispose();
      if (child.material?.metalnessMap) child.material.metalnessMap.dispose();
      if (child.material?.aoMap) child.material.aoMap.dispose();
      if (child.material?.emissiveMap) child.material.emissiveMap.dispose();

      // Dispose animation mixers if any
      if ((child as any).__animationMixer) {
        (child as any).__animationMixer.stopAllAction();
        delete (child as any).__animationMixer;
      }
    });
  }

  /**
   * Remove model from cache
   */
  removeFromCache(characterId: string): void {
    const model = this.cache.get(characterId);
    if (model) {
      this.disposeModel(model);
      this.cache.delete(characterId);
      console.log(`🗑️  Removed from cache: ${characterId}`);
    }
  }

  /**
   * Clear entire cache and dispose all models
   */
  clearCache(): void {
    this.cache.forEach((model) => {
      this.disposeModel(model);
    });
    this.cache.clear();
    this.loadingPromises.clear();
    console.log('🗑️  Model cache cleared');
  }

  /**
   * Get cache statistics
   */
  getCacheStats(): { size: number; characterIds: string[] } {
    return {
      size: this.cache.size,
      characterIds: Array.from(this.cache.keys()),
    };
  }
}
