/**
 * Character System Integration
 * Integrates CharacterManager and ModelLoader with existing Three.js scene
 * Handles model switching, voice updates, and UI state management
 */

import { getCharacterManager } from './CharacterManager.js';
import { getVoiceProfileManager } from '../voice/VoiceProfileManager.js';
import { ModelLoader } from '../models/ModelLoader.js';
import { CHARACTER_REGISTRY, getCharacterProfile } from '../config/characters.js';

let modelLoader: ModelLoader | null = null;
let threejsScene: any = null;
let threeJsPivot: any = null;
let gltfLoader: any = null;

/**
 * Initialize character system with Three.js scene
 */
export function initializeCharacterSystem(
  scene: any,
  pivot: any,
  loader: any
): void {
  threejsScene = scene;
  threeJsPivot = pivot;
  gltfLoader = loader;
  modelLoader = new ModelLoader(loader);

  const characterManager = getCharacterManager();

  // Listen for character change events
  characterManager.on((type, data) => {
    if (type === 'character-change') {
      const event = data as any;
      console.log(`Character changed: ${event.previousCharacterId} → ${event.newCharacterId}`);
      handleCharacterSwitch(event.newCharacterId);
    } else if (type === 'character-error') {
      const error = data as any;
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
function setupCharacterNavigationUI(): void {
  const navButtons = document.querySelectorAll('.character-nav-btn');

  navButtons.forEach((btn: any) => {
    btn.addEventListener('click', async (e: Event) => {
      const characterId = (btn as any).dataset.character;
      await switchToCharacter(characterId, 'user-selection');
      updateCharacterNavUI(characterId);
    });
  });
}

/**
 * Update UI to reflect active character
 */
function updateCharacterNavUI(characterId: string): void {
  const navButtons = document.querySelectorAll('.character-nav-btn');

  navButtons.forEach((btn: any) => {
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
function updateHUDTheme(profile: any): void {
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
 */
export async function switchToCharacter(
  characterId: string,
  reason: 'user-selection' | 'voice-command' | 'system' = 'user-selection'
): Promise<void> {
  const characterManager = getCharacterManager();

  try {
    // Switch character state
    await characterManager.switchCharacter(characterId, reason);

    // Load model
    await loadCharacterModel(characterId);

    // Update voice profile (already done in CharacterManager)
    updateVoiceIndicator(characterId);
  } catch (error) {
    console.error(`Failed to switch character:`, error);
    const characterManager = getCharacterManager();
    characterManager.reportError({
      characterId,
      error: error instanceof Error ? error : new Error(String(error)),
    });
  }
}

/**
 * Load model for character (with smooth fade transition)
 */
async function loadCharacterModel(characterId: string): Promise<void> {
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
function updateSceneModel(characterId: string): void {
  if (!threeJsPivot) return;

  const characterManager = getCharacterManager();
  const model = characterManager.getLoadedModel(characterId);

  if (!model) {
    console.warn(`No model loaded for character: ${characterId}`);
    return;
  }

  // Fade out current models
  threeJsPivot.children.forEach((child: any) => {
    if (child.userData?.characterId) {
      fadeOutModel(child);
    }
  });

  // Add new model with fade in
  const modelClone = model.clone();
  modelClone.userData.characterId = characterId;

  threeJsPivot.add(modelClone);
  setTimeout(() => {
    fadeInModel(modelClone);
  }, 150);
}

/**
 * Fade out model over 300-500ms
 */
function fadeOutModel(model: any, duration: number = 400): void {
  const startOpacity: number = model.userData.opacity ?? 1;
  const startTime = Date.now();

  const animate = () => {
    const elapsed = Date.now() - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const opacity = startOpacity * (1 - progress);

    model.traverse((child: any) => {
      if (child.material) {
        if (Array.isArray(child.material)) {
          child.material.forEach((m: any) => {
            m.opacity = opacity;
          });
        } else {
          child.material.opacity = opacity;
        }
      }
    });

    if (progress < 1) {
      requestAnimationFrame(animate);
    } else {
      // Remove from scene after fade out
      model.parent?.remove(model);
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
function fadeInModel(model: any, duration: number = 400): void {
  const startTime = Date.now();
  model.userData.opacity = 0;

  // Start with opacity 0
  model.traverse((child: any) => {
    if (child.material) {
      if (Array.isArray(child.material)) {
        child.material.forEach((m: any) => {
          m.opacity = 0;
        });
      } else {
        child.material.opacity = 0;
      }
    }
  });

  const animate = () => {
    const elapsed = Date.now() - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const opacity = progress; // Fade from 0 to 1

    model.traverse((child: any) => {
      if (child.material) {
        if (Array.isArray(child.material)) {
          child.material.forEach((m: any) => {
            m.opacity = opacity;
          });
        } else {
          child.material.opacity = opacity;
        }
      }
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
function handleCharacterLoadError(error: any): void {
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
function handleCharacterSwitch(characterId: string): void {
  console.log(`Handling character switch to: ${characterId}`);
}

/**
 * Update voice status indicator based on character
 */
function updateVoiceIndicator(characterId: string): void {
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
function showHUDNotification(message: string, duration: number = 3000): void {
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
export function updateCharacterVisibility(appState: string): void {
  const characterManager = getCharacterManager();
  const currentCharacterId = characterManager.getCurrentCharacterId();

  const ringOwnsStage = [
    'USER_SPEAKING', 'AI_SPEAKING',
    'SPEECH_DETECTED', 'TRANSCRIBING', 'SPEAKING'
  ].includes(appState);
  characterManager.setCharacterVisibility(currentCharacterId, !ringOwnsStage);
  const activeModel = getActiveCharacterModel();
  if (activeModel) activeModel.visible = !ringOwnsStage;
}

/**
 * Export voice profile for TTS requests
 */
export function getCurrentVoiceProfile(): any {
  const voiceManager = getVoiceProfileManager();
  return voiceManager.getActiveProfile();
}

/**
 * Build TTS request using current character voice
 */
export function buildTTSRequest(text: string): Record<string, any> {
  const voiceManager = getVoiceProfileManager();
  return voiceManager.buildTTSRequestBody(text);
}
