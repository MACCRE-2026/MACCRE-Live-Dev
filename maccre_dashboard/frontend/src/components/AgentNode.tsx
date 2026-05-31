import { Handle, Position } from '@xyflow/react';

export default function AgentNode({ data, selected }: any) {
  return (
    <div className={`custom-node agent-node ${selected ? 'selected' : ''}`}>
      <Handle type="target" position={Position.Top} className="node-handle" />
      
      <div className="node-header">
        <div className={`status-dot ${data.isLive ? 'live' : ''}`} />
        <strong>{data.label}</strong>
      </div>
      
      <div className="node-body">
        <span className="agent-role">{data.role || 'Agent'}</span>
        {data.recursion && (
          <div className="recursion-badge">↺ {data.recursion}</div>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} className="node-handle" />
    </div>
  );
}
