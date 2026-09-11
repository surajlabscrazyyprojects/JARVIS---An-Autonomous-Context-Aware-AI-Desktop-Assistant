/**
 * Character Manager (JavaScript)
 * Single source of truth for character state, model management, and transitions
 * Handles character switching, state preservation, and event dispatching
 */

import { CHARACTER_REGISTRY, getCharacterProfile } from '../config/characters.js';
import { getVoiceProfileManager } from '../voice/VoiceProfileManager.js';

/**
 * @class CharacterManager
 */
export class CharacterManager {
  constructor() {
    this.currentCharacterId = 'IRON_MAN';
    this.availableCharacterIds = Object.keys(CHARACTER_REGISTRY);
    this.characterState = new Map();
    this.eventListeners = new Set();
    this.loadedModels = new Map();
    this.isTransitioning = false;

    // Initialize state for all characters
    this.availableCharacterIds.forEach((id) => {
      this.characterState.set(id, {
        currentCharacterId: id,
        scale: 1.0,
        rotationY: 0,
        visible: id === 'IRON_MAN',
      });
      this.loadedModels.set(id, null);
    });

    // Initialize voice profile for current character (uses centralized registry)
    const profile = getCharacterProfile('IRON_MAN');
    getVoiceProfileManager().setActiveCharacter('IRON_MAN');
  }

  /**
   * Get current active character ID
   * @returns {string}
   */
  getCurrentCharacterId() {
    return this.currentCharacterId;
  }

  /**
   * Get current character profile
   * @returns {Object}
   */
  getCurrentCharacterProfile() {
    return getCharacterProfile(this.currentCharacterId);
  }

  /**
   * Get all available character IDs
   * @returns {string[]}
   */
  getAvailableCharacterIds() {
    return [...this.availableCharacterIds];
  }

  /**
   * Switch to a different character
   * @async
   * @param {string} characterId
   * @param {'user-selection'|'voice-command'|'system'} reason
   */
  async switchCharacter(characterId, reason = 'user-selection') {
    // Validation
    if (!this.availableCharacterIds.includes(characterId)) {
      throw new Error(`Character not found: ${characterId}`);
    }

    if (this.currentCharacterId === characterId) {
      console.debug(`Already on character: ${characterId}`);
      return;
    }

    if (this.isTransitioning) {
      console.warn('Character transition in progress, queuing request');
      await new Promise((resolve) => setTimeout(resolve, 500));
    }

    this.isTransitioning = true;

    try {
      const previousCharacterId = this.currentCharacterId;
      const newProfile = getCharacterProfile(characterId);

      // Update voice profile for new character (auto-switches Fish Audio voice model)
      getVoiceProfileManager().setActiveCharacter(characterId);

      // Update current character ID
      this.currentCharacterId = characterId;

      // Emit character change event
      this.emit('character-change', {
        previousCharacterId,
        newCharacterId: characterId,
        timestamp: Date.now(),
        reason,
      });

      // Emit loaded event
      this.emit('character-loaded', newProfile);

      console.log(`✓ Switched to character: ${characterId}`);
    } finally {
      this.isTransitioning = false;
    }
  }

  /**
   * Update character-specific state (scale, rotation, etc.)
   * @param {string} characterId
   * @param {Object} updates - Partial CharacterState
   */
  updateCharacterState(characterId, updates) {
    const state = this.characterState.get(characterId);
    if (!state) {
      console.error(`Character state not found: ${characterId}`);
      return;
    }

    const updated = { ...state, ...updates };
    this.characterState.set(characterId, updated);
    this.emit('state-updated', updated);
  }

  /**
   * Get character state (scale, rotation, visibility)
   * @param {string} characterId
   * @returns {Object|null}
   */
  getCharacterState(characterId) {
    return this.characterState.get(characterId) || null;
  }

  /**
   * Save loaded Three.js model for character
   * @param {string} characterId
   * @param {Object|null} model
   */
  setLoadedModel(characterId, model) {
    if (!this.availableCharacterIds.includes(characterId)) {
      console.error(`Invalid character ID: ${characterId}`);
      return;
    }
    this.loadedModels.set(characterId, model);
  }

  /**
   * Get loaded Three.js model for character
   * @param {string} characterId
   * @returns {Object|null}
   */
  getLoadedModel(characterId) {
    return this.loadedModels.get(characterId) || null;
  }

  /**
   * Check if model is loaded
   * @param {string} characterId
   * @returns {boolean}
   */
  isModelLoaded(characterId) {
    const model = this.loadedModels.get(characterId);
    return model !== null && model !== undefined;
  }

  /**
   * Preserve visible state (for AI speaking state)
   * @param {string} characterId
   * @param {boolean} visible
   */
  setCharacterVisibility(characterId, visible) {
    this.updateCharacterState(characterId, { visible });
  }

  /**
   * Check if character should be visible
   * @param {string} characterId
   * @returns {boolean}
   */
  isCharacterVisible(characterId) {
    const state = this.characterState.get(characterId);
    return state?.visible ?? false;
  }

  /**
   * Subscribe to character events
   * @param {Function} listener
   * @returns {Function} unsubscribe function
   */
  on(listener) {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  }

  /**
   * Emit event to all listeners
   * @private
   * @param {string} type
   * @param {Object} data
   */
  emit(type, data) {
    this.eventListeners.forEach((listener) => {
      try {
        listener(type, data);
      } catch (error) {
        console.error('Error in character event listener:', error);
      }
    });
  }

  /**
   * Report model load error
   * @param {Object} error - ModelLoadError
   */
  reportError(error) {
    this.emit('character-error', error);
  }

  /**
   * Get character for fallback
   * @returns {string}
   */
  getFallbackCharacterId() {
    return 'IRON_MAN'; // Always fall back to Iron Man
  }

  /**
   * Check if is transitioning
   * @returns {boolean}
   */
  isTransitioningNow() {
    return this.isTransitioning;
  }

  /**
   * Reset to initial state
   */
  reset() {
    this.currentCharacterId = 'IRON_MAN';
    this.isTransitioning = false;
    this.characterState.clear();
    this.loadedModels.clear();
    this.eventListeners.clear();
  }
}

// Singleton instance
let instance = null;

/**
 * Get or create singleton instance
 * @returns {CharacterManager}
 */
export function getCharacterManager() {
  if (!instance) {
    instance = new CharacterManager();
  }
  return instance;
}
