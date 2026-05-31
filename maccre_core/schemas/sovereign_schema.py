# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │                   Default params: def f(p:str='') -> None: p=p or root/x   │
# │  IV.  DATACENTER  5-Tier: 01_Raw_Source · 02_Dynamic_Context               │
# │                           03_Agent_Ledgers · 04_Code_Artifacts             │
# │                           05_Rendered_Media                                 │
# │  V.   DIAMOND     Gen: temp=1.0  ·  Critic: temp=0.1 + dataclass schema   │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │
# └─────────────────────────────────────────────────────────────────────────────┘
import typing
import dataclasses
from typing import Any, Type, TypeVar, get_type_hints, get_origin, get_args

T = TypeVar('T')

class SchemaValidationError(Exception):
    """Raised when dictionary mapping to dataclass fails strict type enforcement."""
    pass

def _resolve_type(target_type: Type[Any], value: Any, field_name: str) -> Any:
    """Recursively validates and casts fundamental types, tracking nested dataclasses."""
    
    # 1. Any Unbound Type
    if target_type is Any:
        return value
        
    origin = get_origin(target_type)
    args = get_args(target_type)

    # 2. Handle Optional / Union[X, None]
    if origin is typing.Union:
        if type(None) in args:
            if value is None:
                return None
            
            # Extract the actual target type (e.g., str from Optional[str])
            real_type = next(a for a in args if a is not type(None))
            return _resolve_type(real_type, value, field_name)
        
        # We don't support complex Unions (Union[str, int]) natively without overhead
        return value 

    # 3. Handle Lists (List[T])
    if origin is list or origin is typing.List:
        if not isinstance(value, list):
            raise SchemaValidationError(f"Field '{field_name}' expects a list, got {type(value).__name__}.")
        
        if args:
            inner_type = args[0]
            return [_resolve_type(inner_type, item, f"{field_name}[]") for item in value]
        return value

    # 4. Handle Dicts (Dict[K, V])
    if origin is dict or origin is typing.Dict:
        if not isinstance(value, dict):
            raise SchemaValidationError(f"Field '{field_name}' expects a dict, got {type(value).__name__}.")
        
        if len(args) == 2:
            k_type, v_type = args
            return {
                _resolve_type(k_type, k, f"{field_name}[key]"): _resolve_type(v_type, v, f"{field_name}[value]")
                for k, v in value.items()
            }
        return value

    # 5. Handle Nested Dataclasses
    if dataclasses.is_dataclass(target_type):
        if not isinstance(value, dict):
            raise SchemaValidationError(f"Field '{field_name}' expects nested object mapping to {target_type.__name__}, got {type(value).__name__}.")
        return dict_to_dataclass(target_type, value)

    # 6. Base Type Casting (int, float, str, bool)
    if isinstance(target_type, type) and issubclass(target_type, (int, float, str, bool)):
        if value is None:
            raise SchemaValidationError(f"Field '{field_name}' cannot be None for type {target_type.__name__}")
        try:
            # Handle strict boolean parsing from strings to prevent bool('False') == True
            if target_type is bool and isinstance(value, str):
                return value.lower() in ('true', '1', 'yes')
            return target_type(value)
        except (ValueError, TypeError):
            raise SchemaValidationError(f"Field '{field_name}' failed to cast {repr(value)} to {target_type.__name__}.")
            
    # Ultimate Fallback
    return value

def dict_to_dataclass(cls: Type[T], data: dict[str, Any]) -> T:
    """
    Instantiates a dataclass from a raw dictionary, mirroring Pydantic's strict type enforcement.
    Raises SchemaValidationError on failure.
    """
    if not dataclasses.is_dataclass(cls):
        raise TypeError(f"{cls.__name__} is not a valid standard dataclass.")
        
    hints = get_type_hints(cls)
    kwargs = {}
    
    for field in dataclasses.fields(cls):
        field_type = hints.get(field.name, field.type)
        
        if field.name not in data:
            # Check if it has a default
            if field.default is not dataclasses.MISSING:
                continue
            if field.default_factory is not dataclasses.MISSING:
                continue
                
            # If Optional, it's safe to skip if missing
            origin = get_origin(field_type)
            args = get_args(field_type)
            if origin is typing.Union and type(None) in args:
                kwargs[field.name] = None
                continue
                
            raise SchemaValidationError(f"Required field '{field.name}' is missing.")
            
        raw_val = data[field.name]
        kwargs[field.name] = _resolve_type(field_type, raw_val, field.name)
        
    return cls(**kwargs)

def dataclass_to_dict(obj: Any) -> dict[str, Any]:
    """Helper un-mapper to reverse the object into JSON state."""
    if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
        raise TypeError("Object must be a dataclass instance (not a class).")
    return dataclasses.asdict(obj)
