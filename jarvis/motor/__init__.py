"""
jarvis.motor
============
JARVIS motor subsystem: deterministic mouse + keyboard control with smooth,
deliberate motion and a safety watchdog (spec sections 10-16, 43, 49-50).

Separation of responsibility:
  * Vision  answers "WHAT is visible?"
  * Planner answers "WHAT should I do next?"
  * Motor   answers "HOW do I physically perform that action?"
  * Verifier answers "DID the intended result happen?"
"""
from __future__ import annotations

from jarvis.motor.keyboard import KeyboardController
from jarvis.motor.mouse import MouseController
from jarvis.motor.planner import MotorPlan, MotorPlanner
from jarvis.motor.trajectory import Trajectory, build_trajectory, line_points, circle_points
from jarvis.motor.watchdog import InputSafetyWatchdog

__all__ = [
    "InputSafetyWatchdog",
    "KeyboardController",
    "MotorPlan",
    "MotorPlanner",
    "MouseController",
    "Trajectory",
    "build_trajectory",
    "circle_points",
    "line_points",
]