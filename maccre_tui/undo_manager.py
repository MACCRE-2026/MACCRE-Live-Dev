"""
maccre_tui/undo_manager.py
===========================
Undo/Redo Manager — Command pattern implementation for flow editing.

Phase 6: Provides undo/redo functionality for flow topology operations.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)


class Command(ABC):
    """Abstract base class for undoable commands."""
    
    @abstractmethod
    def execute(self) -> None:
        """Execute the command."""
        pass
    
    @abstractmethod
    def undo(self) -> None:
        """Undo the command."""
        pass
    
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of this command."""
        pass


class AddNodeCommand(Command):
    """Command to add a node to the flow."""
    
    def __init__(self, flow_steps: list[Any], node: Any, position: int | None = None):
        """Initialize add node command.
        
        Args:
            flow_steps: Reference to active_flow_steps list
            node: FlowStep to add
            position: Index to insert at (None = append)
        """
        self.flow_steps = flow_steps
        self.node = node
        self.position = position
        self.actual_position: int | None = None
    
    def execute(self) -> None:
        """Add the node to the flow."""
        if self.position is None:
            self.flow_steps.append(self.node)
            self.actual_position = len(self.flow_steps) - 1
        else:
            self.flow_steps.insert(self.position, self.node)
            self.actual_position = self.position
        logger.info(f"[Undo] Executed: Add node {self.node.macronode_name} at position {self.actual_position}")
    
    def undo(self) -> None:
        """Remove the node from the flow."""
        if self.actual_position is not None and self.actual_position < len(self.flow_steps):
            removed = self.flow_steps.pop(self.actual_position)
            logger.info(f"[Undo] Undid: Remove node {removed.macronode_name} from position {self.actual_position}")
    
    def description(self) -> str:
        return f"Add {self.node.macronode_name}"


class DeleteNodeCommand(Command):
    """Command to delete a node from the flow."""
    
    def __init__(self, flow_steps: list[Any], position: int):
        """Initialize delete node command.
        
        Args:
            flow_steps: Reference to active_flow_steps list
            position: Index of node to delete
        """
        self.flow_steps = flow_steps
        self.position = position
        self.deleted_node: Any | None = None
    
    def execute(self) -> None:
        """Delete the node from the flow."""
        if 0 <= self.position < len(self.flow_steps):
            self.deleted_node = self.flow_steps.pop(self.position)
            logger.info(f"[Undo] Executed: Delete node {self.deleted_node.macronode_name} from position {self.position}")
    
    def undo(self) -> None:
        """Restore the deleted node."""
        if self.deleted_node is not None:
            self.flow_steps.insert(self.position, self.deleted_node)
            logger.info(f"[Undo] Undid: Restore node {self.deleted_node.macronode_name} at position {self.position}")
    
    def description(self) -> str:
        if self.deleted_node:
            return f"Delete {self.deleted_node.macronode_name}"
        return "Delete node"


class MoveNodeCommand(Command):
    """Command to move a node within the flow."""
    
    def __init__(self, flow_steps: list[Any], from_pos: int, to_pos: int):
        """Initialize move node command.
        
        Args:
            flow_steps: Reference to active_flow_steps list
            from_pos: Current index of node
            to_pos: Target index for node
        """
        self.flow_steps = flow_steps
        self.from_pos = from_pos
        self.to_pos = to_pos
        self.node: Any | None = None
    
    def execute(self) -> None:
        """Move the node to new position."""
        if 0 <= self.from_pos < len(self.flow_steps):
            self.node = self.flow_steps.pop(self.from_pos)
            # Adjust to_pos if needed (due to pop)
            adjusted_to = self.to_pos if self.to_pos < self.from_pos else self.to_pos - 1
            self.flow_steps.insert(adjusted_to, self.node)
            logger.info(f"[Undo] Executed: Move node {self.node.macronode_name} from {self.from_pos} to {adjusted_to}")
    
    def undo(self) -> None:
        """Move the node back to original position."""
        if self.node is not None:
            # Find current position of the node
            try:
                current_pos = self.flow_steps.index(self.node)
                self.flow_steps.pop(current_pos)
                self.flow_steps.insert(self.from_pos, self.node)
                logger.info(f"[Undo] Undid: Move node {self.node.macronode_name} back to {self.from_pos}")
            except ValueError:
                logger.error("[Undo] Failed to find node for undo move")
    
    def description(self) -> str:
        if self.node:
            return f"Move {self.node.macronode_name}"
        return "Move node"


class ConfigureNodeCommand(Command):
    """Command to configure a node's properties."""
    
    def __init__(self, node: Any, old_config: dict[str, Any], new_config: dict[str, Any]):
        """Initialize configure node command.
        
        Args:
            node: FlowStep to configure
            old_config: Previous configuration state
            new_config: New configuration state
        """
        self.node = node
        self.old_config = deepcopy(old_config)
        self.new_config = deepcopy(new_config)
    
    def execute(self) -> None:
        """Apply new configuration to node."""
        self._apply_config(self.new_config)
        logger.info(f"[Undo] Executed: Configure node {self.node.macronode_name}")
    
    def undo(self) -> None:
        """Restore old configuration to node."""
        self._apply_config(self.old_config)
        logger.info(f"[Undo] Undid: Restore config for node {self.node.macronode_name}")
    
    def _apply_config(self, config: dict[str, Any]) -> None:
        """Apply configuration to node."""
        if "name" in config:
            self.node.macronode_name = config["name"]
        if "payload_mode" in config:
            self.node.payload_mode = config["payload_mode"]
        if "custom_instructions" in config:
            self.node.custom_instructions = config["custom_instructions"]
        if "agent_tools_overrides" in config:
            self.node.agent_tools_overrides = deepcopy(config["agent_tools_overrides"])
        if "node_config" in config:
            self.node.config = deepcopy(config["node_config"])
    
    def description(self) -> str:
        return f"Configure {self.node.macronode_name}"


class BatchCommand(Command):
    """Command that executes multiple commands as one atomic operation."""
    
    def __init__(self, commands: list[Command], description_text: str = "Batch operation"):
        """Initialize batch command.
        
        Args:
            commands: List of commands to execute as a batch
            description_text: Description for the entire batch
        """
        self.commands = commands
        self.description_text = description_text
    
    def execute(self) -> None:
        """Execute all commands in order."""
        for cmd in self.commands:
            cmd.execute()
        logger.info(f"[Undo] Executed: Batch of {len(self.commands)} commands")
    
    def undo(self) -> None:
        """Undo all commands in reverse order."""
        for cmd in reversed(self.commands):
            cmd.undo()
        logger.info(f"[Undo] Undid: Batch of {len(self.commands)} commands")
    
    def description(self) -> str:
        return self.description_text


class UndoManager:
    """Manages undo/redo stack for flow editing operations.
    
    Phase 6: Provides undo/redo functionality with configurable stack size.
    """
    
    def __init__(self, max_stack_size: int = 50):
        """Initialize undo manager.
        
        Args:
            max_stack_size: Maximum number of commands to keep in history
        """
        self.max_stack_size = max_stack_size
        self.undo_stack: list[Command] = []
        self.redo_stack: list[Command] = []
    
    def execute_command(self, command: Command) -> None:
        """Execute a command and add it to undo stack.
        
        Args:
            command: Command to execute
        """
        command.execute()
        self.undo_stack.append(command)
        
        # Enforce max stack size
        if len(self.undo_stack) > self.max_stack_size:
            self.undo_stack.pop(0)
        
        # Clear redo stack when new command is executed
        self.redo_stack.clear()
        
        logger.debug(f"[UndoManager] Command executed: {command.description()}")
    
    def undo(self) -> bool:
        """Undo the most recent command.
        
        Returns:
            True if undo was successful, False if nothing to undo
        """
        if not self.undo_stack:
            logger.debug("[UndoManager] Nothing to undo")
            return False
        
        command = self.undo_stack.pop()
        command.undo()
        self.redo_stack.append(command)
        
        logger.info(f"[UndoManager] Undid: {command.description()}")
        return True
    
    def redo(self) -> bool:
        """Redo the most recently undone command.
        
        Returns:
            True if redo was successful, False if nothing to redo
        """
        if not self.redo_stack:
            logger.debug("[UndoManager] Nothing to redo")
            return False
        
        command = self.redo_stack.pop()
        command.execute()
        self.undo_stack.append(command)
        
        logger.info(f"[UndoManager] Redid: {command.description()}")
        return True
    
    def can_undo(self) -> bool:
        """Check if undo is available."""
        return len(self.undo_stack) > 0
    
    def can_redo(self) -> bool:
        """Check if redo is available."""
        return len(self.redo_stack) > 0
    
    def get_undo_description(self) -> str | None:
        """Get description of next undo operation."""
        if self.undo_stack:
            return self.undo_stack[-1].description()
        return None
    
    def get_redo_description(self) -> str | None:
        """Get description of next redo operation."""
        if self.redo_stack:
            return self.redo_stack[-1].description()
        return None
    
    def clear(self) -> None:
        """Clear both undo and redo stacks."""
        self.undo_stack.clear()
        self.redo_stack.clear()
        logger.info("[UndoManager] Cleared undo/redo history")
