/**
 * Character Type Definitions (JavaScript)
 * Production-grade typing for multi-character support
 */

// No runtime exports needed - these are type definitions for documentation
// In actual use, objects will conform to these shapes

/**
 * @typedef {Object} CharacterVoiceProfile
 * @property {string} id
 * @property {string} referenceId - Fish Audio reference ID
 * @property {string} name
 * @property {string} accent
 * @property {number} speed - Default speech rate
 * @property {Object.<string, {speed: number}>} emotionalRange
 */

/**
 * @typedef {Object} CharacterAnimationSet
 * @property {string|null} idle
 * @property {string|null} speaking
 * @property {string|null} thinking
 * @property {string|null} gesture
 * @property {string|null} combat
 */

/**
 * @typedef {Object} CharacterModel
 * @property {string} id
 * @property {string} path
 * @property {number} scale
 * @property {Object} defaultPosition
 * @property {Object} defaultRotation
 * @property {Object} materialOverride
 */

/**
 * @typedef {Object} CharacterProfile
 * @property {string} id
 * @property {string} displayName
 * @property {CharacterModel} model
 * @property {CharacterVoiceProfile} voiceProfile
 * @property {CharacterAnimationSet} animationSet
 * @property {boolean} handTrackingEnabled
 * @property {string} description
 * @property {string} color - HUD accent color (hex)
 * @property {string} [systemPrompt]
 * @property {string} [memoryStyle]
 * @property {string} [emotionStyle]
 * @property {string} [animationStyle]
 */

/**
 * @typedef {Object} CharacterState
 * @property {string} currentCharacterId
 * @property {number} scale
 * @property {number} rotationY
 * @property {boolean} visible
 */

/**
 * @typedef {Object} CharacterChangeEvent
 * @property {string} previousCharacterId
 * @property {string} newCharacterId
 * @property {number} timestamp
 * @property {'user-selection'|'voice-command'|'system'} reason
 */

/**
 * @typedef {Object} ModelLoadError
 * @property {string} characterId
 * @property {Error} error
 * @property {string} [fallbackToCharacterId]
 */

export {};
