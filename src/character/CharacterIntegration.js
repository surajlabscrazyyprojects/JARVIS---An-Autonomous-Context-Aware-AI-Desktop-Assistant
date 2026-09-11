/**
 * Character System Integration (JavaScript)
 * Integrates CharacterManager and ModelLoader with existing Three.js scene.
 * Handles model switching, animation mixers, rendering-pipeline registration,
 * voice updates, and UI state management.
 *
 * Counterpart of CharacterIntegration.ts — the browser loads this module.
 */

import { getCharacterManager } from './CharacterManager.js';
import { getVoiceProfileManager } from '../voice/VoiceProfileManager.js';
import { ModelLoader } from '../models/ModelLoader.js';
import { CHARACTER_REGISTRY, getCharacterProfile } from '../config/characters.js';

let modelLoader = null;
let threejsScene = null;
let threeJsPivot = null;
let gltfLoader = null;
let threeRef = null;
let renderingPipeline = null;

/**
 * Initialize character system with Three.js scene
 * @param {Object} scene
 * @param {Object} pivot
 * @param {Object} loader
 * @param {Object} [THREE]
 * @param {Object} [camera]
 */
export function initializeCharacterSystem(scene, pivot, loader, THREE, camera) {
  threejsScene = scene;
  threeJsPivot = pivot;
  gltfLoader = loader;
  threeRef = THREE || (typeof window !== 'undefined' ? window.THREE : null);
  modelLoader = new ModelLoader(loader, threeRef);

  const characterManager = getCharacterManager();

  // Listen for character change events
  characterManager.on((type, data) => {
    if (type === 'character-change') {
      const event = data;
      console.log(`Character changed: ${event.previousCharacterId} -> ${event.newCharacterId}`);
      handleCharacterSwitch(event.newCharacterId);
    } else if (type === 'character-error') {
      const error = data;
      console.error(`Character error: ${error.characterId}`, error.error);
      handleCharacterLoadError(error);
    }
  });

  // Setup UI event listeners
  setupCharacterNavigationUI();

  console.log('✓ Character system initialized');
}

/**
 * Setup character navigation UI buttons
 */
function setupCharacterNavigationUI() {
  const navButtons = document.querySelectorAll('.character-nav-btn');

  navButtons.forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      const characterId = btn.dataset.character;
      await switchToCharacter(characterId, 'user-selection');
      updateCharacterNavUI(characterId);
    });
  });
}

/**
 * Update UI to reflect active character
 */
function updateCharacterNavUI(characterId) {
  const navButtons = document.querySelectorAll('.character-nav-btn');

  navButtons.forEach((btn) => {
    if (btn.dataset.character === characterId) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  // Update HUD color scheme based on character
  const profile = getCharacterProfile(characterId);
  updateHUDTheme(profile);
}

/**
 * Update HUD visual theme based on character
 */
function updateHUDTheme(profile) {
  const root = document.documentElement;

  // Update primary accent color
  const color = profile.color || '#00d4ff';
  root.style.setProperty('--character-accent', color);

  // Optional: Update UI element colors based on character theme
  const navContainer = document.getElementById('character-nav-container');
  if (navContainer) {
    navContainer.style.setProperty('--accent-color', color);
  }
}

/**
 * Switch to a different character
 * @param {string} characterId
 * @param {'user-selection'|'voice-command'|'system'} [reason]
 */
export async function switchToCharacter(characterId, reason = 'user-selection') {
  const characterManager = getCharacterManager();

  try {
    // Switch character state
    await characterManager.switchCharacter(characterId, reason);

    // Load model
    await loadCharacterModel(characterId);

    // Update voice profile (already done in CharacterManager)
    updateVoiceIndicator(characterId);
  } catch (error) {
    console.error('Failed to switch character:', error);
    const cm = getCharacterManager();
    cm.reportError({
      characterId,
      error: error instanceof Error ? error : new Error(String(error)),
    });
  }
}

/**
 * Load model for character (with smooth fade transition)
 */
async function loadCharacterModel(characterId) {
  if (!modelLoader || !threeJsPivot) {
    console.error('Character system not initialized');
    return;
  }

  const characterManager = getCharacterManager();
  const profile = getCharacterProfile(characterId);

  try {
    // Check if model is already loaded
    if (characterManager.isModelLoaded(characterId)) {
      console.log(`Model already loaded: ${characterId}`);
      updateSceneModel(characterId);
      return;
    }

    // Load model
    console.log(`Loading model for: ${characterId}`);
    const model = await modelLoader.loadModel(profile, {
      onProgress: (progress) => {
        console.log(`Loading ${characterId}: ${Math.round(progress)}%`);
      },
      onError: (error) => {
        console.error(`Error loading ${characterId}:`, error);
      },
    });

    // Store loaded model in manager
    characterManager.setLoadedModel(characterId, model);

    // Update scene with new model
    updateSceneModel(characterId);
  } catch (error) {
    console.error(`Failed to load model for ${characterId}:`, error);
    throw error;
  }
}

/**
 * Update Three.js scene with character model
 * Handles smooth transitions without recreating scene
 */
function updateSceneModel(characterId) {
  if (!threeJsPivot) return;

  const characterManager = getCharacterManager();
  const model = characterManager.getLoadedModel(characterId);

  if (!model) {
    console.warn(`No model loaded for character: ${characterId}`);
    return;
  }

  // Fade out current models
  threeJsPivot.children.forEach((child) => {
    if (child.userData && child.userData.characterId) {
      fadeOutModel(child);
    }
  });

  // Add new model with fade in
  const skeletonUtils = threeRef && threeRef.SkeletonUtils;
  const modelClone = skeletonUtils && typeof skeletonUtils.clone === 'function'
    ? skeletonUtils.clone(model)
    : (model.clone ? model.clone(true) : model);
  modelClone.userData.characterId = characterId;

  // Set up animation mixers for this clone
  setupAnimationMixer(modelClone);

  threeJsPivot.add(modelClone);

  // Register with the rendering pipeline automatically on EVERY attach so the
  // hologram/wireframe material cache stays in sync with the scene.
  if (renderingPipeline && typeof renderingPipeline.registerCharacter === 'function') {
    try {
      renderingPipeline.registerCharacter(characterId, modelClone);
    } catch (err) {
      console.warn('[CharacterIntegration] Pipeline register failed:', err);
    }
  }

  setTimeout(() => {
    fadeInModel(modelClone);
  }, 150);
}

/**
 * Attach AnimationMixer(s) to a model clone and play its clips.
 * Mixers are stored on the root object's userData so updateAnimations(dt)
 * and ModelLoader.disposeModel can find them.
 */
function setupAnimationMixer(model) {
  if (!threeRef) return;
  const THREE = threeRef;
  const clips = (model.userData && model.userData.animations) || [];
  if (!clips.length) return;

  try {
    const mixer = new THREE.AnimationMixer(model);
    clips.forEach((clip) => {
      try {
        const action = mixer.clipAction(clip);
        action.play();
      } catch (err) {
        console.warn('[CharacterIntegration] clipAction failed:', err);
      }
    });
    model.userData.animationMixer = mixer;
  } catch (err) {
    console.warn('[CharacterIntegration] AnimationMixer unavailable:', err);
  }
}

/**
 * Advance all character animation mixers by delta time.
 * Called every frame from the HUD animate loop.
 */
export function updateAnimations(dt) {
  if (!threeJsPivot) return;
  for (const child of threeJsPivot.children) {
    const mixer = child.userData && child.userData.animationMixer;
    if (mixer && typeof mixer.update === 'function') {
      try {
        mixer.update(dt);
      } catch (err) {
        // Ignore per-mixer errors; keep the loop alive
      }
    }
  }
}

/**
 * Get the model currently attached to the scene for the active character
 * @returns {Object|null}
 */
export function getActiveCharacterModel() {
  const characterManager = getCharacterManager();
  const currentId = characterManager.getCurrentCharacterId();

  if (threeJsPivot) {
    const attached = threeJsPivot.children.find(
      (child) => child.userData && child.userData.characterId === currentId
    );
    if (attached) return attached;
  }
  return characterManager.getLoadedModel(currentId) || null;
}

/**
 * Get the CharacterManager singleton
 * @returns {Object}
 */
export function getCharacterManagerInstance() {
  return getCharacterManager();
}

/**
 * Get the ModelLoader singleton
 * @returns {Object|null}
 */
export function getModelLoaderInstance() {
  return modelLoader;
}

/**
 * Register the rendering pipeline so models are auto-registered on attach
 * @param {Object} pipeline
 */
export function setRenderingPipeline(pipeline) {
  renderingPipeline = pipeline;
  if (pipeline && typeof pipeline.registerCharacter === 'function') {
    const characterManager = getCharacterManager();
    const currentId = characterManager.getCurrentCharacterId();
    const model = getActiveCharacterModel();
    if (model) {
      try {
        pipeline.registerCharacter(currentId, model);
      } catch (err) {
        console.warn('[CharacterIntegration] Pipeline register failed:', err);
      }
    }
  }
}

/**
 * Set a material's opacity as a fraction (0..1) of its *natural* opacity.
 * Pipeline-managed (hologram/wireframe) materials are translucent by design
 * (additive blending), so their target is userData.baseOpacity — never 1.0.
 * Otherwise every fresh load (boot / character switch) blows them out to full
 * additive brightness. Plain materials keep the original 0..1 behaviour.
 */
function _fadeMaterialTo(material, factor) {
  const mats = Array.isArray(material) ? material : [material];
  for (const m of mats) {
    if (!m) continue;
    const base = m._pipelineManaged ? (m.userData?.baseOpacity ?? m.opacity) : 1;
    m.opacity = base * factor;
  }
}

/**
 * Fade out model over 300-500ms
 */
function fadeOutModel(model, duration = 400) {
  const startTime = Date.now();

  const animate = () => {
    const elapsed = Date.now() - startTime;
    const progress = Math.min(elapsed / duration, 1);

    model.traverse((child) => {
      if (child.material) _fadeMaterialTo(child.material, 1 - progress);
    });

    if (progress < 1) {
      requestAnimationFrame(animate);
    } else {
      // Remove from scene after fade out
      if (model.parent) {
        model.parent.remove(model);
      }
      // Dispose resources
      if (modelLoader) {
        modelLoader.disposeModel(model);
      }
    }
  };

  animate();
}

/**
 * Fade in model over 300-500ms
 */
function fadeInModel(model, duration = 400) {
  const startTime = Date.now();
  model.userData.opacity = 0;

  // Start fully transparent (respects each material's natural opacity)
  model.traverse((child) => {
    if (child.material) _fadeMaterialTo(child.material, 0);
  });

  const animate = () => {
    const elapsed = Date.now() - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const opacity = progress; // Fade from 0 to its natural opacity

    model.traverse((child) => {
      if (child.material) _fadeMaterialTo(child.material, progress);
    });

    if (progress < 1) {
      requestAnimationFrame(animate);
    } else {
      model.userData.opacity = 1;
    }
  };

  animate();
}

/**
 * Handle character load error with fallback
 */
function handleCharacterLoadError(error) {
  const characterManager = getCharacterManager();
  const fallbackId = characterManager.getFallbackCharacterId();

  console.warn(`Switching to fallback character: ${fallbackId}`);

  // Show HUD notification
  showHUDNotification(
    `Failed to load ${error.characterId}. Falling back to ${fallbackId}.`
  );

  // Switch to fallback
  switchToCharacter(fallbackId, 'system');
}

/**
 * Handle initial character switch when navigation changes
 */
function handleCharacterSwitch(characterId) {
  console.log(`Handling character switch to: ${characterId}`);
}

/**
 * Update voice status indicator based on character
 */
function updateVoiceIndicator(characterId) {
  const profile = getCharacterProfile(characterId);
  const voiceManager = getVoiceProfileManager();

  // Update status indicator (if exists in DOM)
  const statusEl = document.getElementById('voice-status-indicator');
  if (statusEl) {
    const voiceDesc = voiceManager.getVoiceDescription();
    statusEl.textContent = `VOICE: ${voiceDesc}`;
  }
}

/**
 * Show HUD notification message
 */
function showHUDNotification(message, duration = 3000) {
  const statusEl = document.getElementById('tracking-status');
  if (statusEl) {
    const original = statusEl.textContent;
    statusEl.textContent = message;
    statusEl.style.opacity = '1';

    setTimeout(() => {
      statusEl.textContent = original;
      statusEl.style.opacity = '0';
    }, duration);
  }
}

/**
 * Check if character should be visible based on app state
 */
export function updateCharacterVisibility(appState) {
  const characterManager = getCharacterManager();
  const currentCharacterId = characterManager.getCurrentCharacterId();

  if (appState === 'IDLE' || appState === 'PROCESSING') {
    characterManager.setCharacterVisibility(currentCharacterId, true);
  } else if (appState === 'USER_SPEAKING' || appState === 'AI_SPEAKING') {
    characterManager.setCharacterVisibility(currentCharacterId, false);
  }
}

/**
 * Export voice profile for TTS requests
 */
export function getCurrentVoiceProfile() {
  const voiceManager = getVoiceProfileManager();
  return voiceManager.getActiveProfile();
}

/**
 * Build TTS request using current character voice
 */
export function buildTTSRequest(text) {
  const voiceManager = getVoiceProfileManager();
  return voiceManager.buildTTSRequestBody(text);
}