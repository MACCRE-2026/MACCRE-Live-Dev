import { useState, useCallback } from 'react';
import {
  ReactFlow,
  Controls,
  Background,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
  useReactFlow,
  ReactFlowProvider,
  type NodeChange,
  type EdgeChange,
  type Node,
  type Edge
} from '@xyflow/react';
import { Play, Pause, FastForward, Rewind, Settings, TerminalSquare, ActivitySquare, Send } from 'lucide-react';
import AgentNode from './components/AgentNode';
import Miniboard from './components/Miniboard';
import LeftPanel from './components/LeftPanel';
import GlobalTelemetryBoard from './components/GlobalTelemetryBoard';
import SwarmMonitorTerminal from './components/SwarmMonitorTerminal';
import NudgeModal from './components/NudgeModal';
import './App.css';

const nodeTypes = {
  agentNode: AgentNode,
  loopNode: AgentNode,
};

let idCounter = 1;
const getId = () => `node_${idCounter++}`;

function DashboardEngine() {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [isPlaying, setIsPlaying] = useState(false);
  
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [telemetryBlinking, setTelemetryBlinking] = useState(false);
  const [showTelemetry, setShowTelemetry] = useState(false);
  const [showSwarmMonitor, setShowSwarmMonitor] = useState(false);

  const [showNudgeModal, setShowNudgeModal] = useState(false);
  const [nudgeTarget, setNudgeTarget] = useState<string | null>(null);

  const { screenToFlowPosition } = useReactFlow();

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setNodes((nds) => applyNodeChanges(changes, nds)),
    []
  );
  
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );

  const onConnect = useCallback(
    (params: any) => setEdges((eds) => addEdge({ ...params, animated: true, style: { stroke: '#00ffcc', strokeWidth: 2 } }, eds)),
    []
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();

      const type = event.dataTransfer.getData('application/reactflow');
      if (typeof type === 'undefined' || !type) return;

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const isFirst = nodes.length === 0;
      
      const newNode: Node = {
        id: isFirst ? 'start' : getId(),
        type,
        position,
        data: { 
          label: isFirst ? 'START_NODE' : (type === 'loopNode' ? 'WAIT/RETRY' : 'Unassigned Agent'),
          isLive: false,
          recursion: type === 'loopNode' ? 3 : undefined
        },
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [screenToFlowPosition, nodes.length],
  );

  const onNodeClick = useCallback((_: any, node: Node) => {
    setSelectedAgentId(node.id);
  }, []);

  const updateNodeData = useCallback((nodeId: string, newData: any) => {
    setNodes((nds) =>
      nds.map((n) => {
        if (n.id === nodeId) {
          return { ...n, data: { ...n.data, ...newData } };
        }
        return n;
      })
    );
  }, [setNodes]);

  const updateMultipleNodesData = useCallback((updates: { id: string, data: any }[]) => {
    setNodes((nds) => {
      const ndsCopy = [...nds];
      updates.forEach(update => {
        const idx = ndsCopy.findIndex(n => n.id === update.id);
        if (idx >= 0) {
          ndsCopy[idx] = { ...ndsCopy[idx], data: { ...ndsCopy[idx].data, ...update.data } };
        }
      });
      return ndsCopy;
    });
  }, [setNodes]);

  const togglePlayState = async () => {
    const newState = !isPlaying;
    setIsPlaying(newState);
    
    if (newState) {
      const topologyPayload = { nodes, edges };
      console.log("Compiling visual topology to Workbook JSON...", topologyPayload);
      setTelemetryBlinking(true);
      try {
        await fetch('http://127.0.0.1:8000/api/control/compile', { 
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(topologyPayload)
        });
      } catch (e) { console.error(e); }
    } else {
      setTelemetryBlinking(false);
      try {
        await fetch('http://127.0.0.1:8000/api/control/pause', { method: 'POST' });
      } catch (e) { console.error(e); }
    }
  };

  const handleOpenTelemetry = () => {
    setTelemetryBlinking(false);
    setShowTelemetry(true);
  };

  const handleNudgeSubmit = async (target: string, payload: string) => {
    try {
      await fetch('http://127.0.0.1:8000/api/control/nudge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_id: "ALL", // OmniDashboard nudges affect active jobs
          target_node: target,
          payload_text: payload
        })
      });
    } catch (e) {
      console.error("Nudge failed:", e);
    }
  };

  const selectedAgent = nodes.find(n => n.id === selectedAgentId);

  return (
    <div className="dashboard-container">
      <LeftPanel />

      <button 
        className="icon-btn" 
        onClick={() => setShowSwarmMonitor(true)}
        style={{ position: 'absolute', top: '80px', left: '24px', zIndex: 300, background: 'rgba(0,0,0,0.5)', padding: '8px', borderRadius: '8px', border: '1px solid var(--panel-border)' }}
        title="Open Swarm Monitor Terminal"
      >
        <ActivitySquare size={24} color="var(--accent)" />
      </button>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onDragOver={onDragOver}
        onDrop={onDrop}
        defaultViewport={{ x: 0, y: 0, zoom: 0.5 }}
        minZoom={0.2}
        className="react-flow-dark react-flow-bounded"
      >
        <Background color="#333" gap={16} />
        <Controls showInteractive={false} />
      </ReactFlow>

      <Miniboard 
        key={selectedAgentId || 'none'}
        agent={selectedAgent} 
        onClose={() => setSelectedAgentId(null)} 
        allNodes={nodes}
        onUpdateNode={updateNodeData}
        onUpdateMultipleNodes={updateMultipleNodesData}
      />

      <GlobalTelemetryBoard 
        isOpen={showTelemetry}
        onClose={() => setShowTelemetry(false)}
      />

      <SwarmMonitorTerminal
        isOpen={showSwarmMonitor}
        onClose={() => setShowSwarmMonitor(false)}
        activeNodes={nodes.filter(n => n.data.label !== 'START_NODE' && n.data.label !== 'WAIT/RETRY' && n.data.label !== 'Unassigned Agent')}
        onNudgeRequest={(nodeId: string) => {
          setNudgeTarget(nodeId);
          setShowNudgeModal(true);
        }}
      />

      <div className="vcr-bar">
        <button className="vcr-btn" title="Restart Topology"><Rewind /></button>
        <button className={`vcr-btn ${isPlaying ? 'active' : ''}`} onClick={togglePlayState} title={isPlaying ? "Pause Swarm (Inject HITL)" : "Ignite / Compile Swarm"}>
          {isPlaying ? <Pause /> : <Play />}
        </button>
        <button className="vcr-btn" title="Step Forward"><FastForward /></button>
        <div style={{ width: '1px', height: '32px', background: 'var(--panel-border)', margin: '0 8px' }} />
        <button 
          className="vcr-btn" 
          title="Global Swarm Nudge" 
          onClick={() => { setNudgeTarget(null); setShowNudgeModal(true); }}
        >
          <Send color="var(--accent)" />
        </button>
        <button className={`vcr-btn ${telemetryBlinking ? 'blink-active' : ''}`} onClick={handleOpenTelemetry} title="View Sanitized Telemetry Smoke Test">
          <TerminalSquare />
        </button>
        <button className="vcr-btn" title="Global Settings"><Settings /></button>
      </div>

      <NudgeModal 
        isOpen={showNudgeModal}
        onClose={() => setShowNudgeModal(false)}
        targetNode={nudgeTarget}
        onSubmit={handleNudgeSubmit}
      />
    </div>
  );
}

export default function App() {
  return (
    <ReactFlowProvider>
      <DashboardEngine />
    </ReactFlowProvider>
  );
}
