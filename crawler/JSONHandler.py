import json
from pathlib import Path
from typing import Any, Union, List, Dict

class JSONHandler:
    def __init__(self, file_path: Union[str, Path] = None):
        """
        Initialize JSON handler, optionally loading from file
        
        Args:
            file_path: Path to JSON file to load initially
        """
        self.data = {}
        self.file_path = Path(file_path) if file_path else None
        if self.file_path and self.file_path.exists():
            self.load()

    def load(self, file_path: Union[str, Path] = None) -> bool:
        """
        Load JSON data from file
        
        Args:
            file_path: Path to JSON file (uses self.file_path if None)
        
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        try:
            path = Path(file_path) if file_path else self.file_path
            if not path or not path.exists():
                return False
                
            with open(path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            self.file_path = path
            return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading JSON: {e}")
            return False

    def save(self, file_path: Union[str, Path] = None) -> bool:
        """
        Save JSON data to file
        
        Args:
            file_path: Path to save to (uses self.file_path if None)
        
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            path = Path(file_path) if file_path else self.file_path
            if not path:
                raise ValueError("No file path specified")
            
            # Create parent directories if they don't exist
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            
            return True
        except (IOError, TypeError, OSError) as e:
            print(f"Error saving JSON: {e}")
            return False
        
    def isEmpty(self) -> bool:
        return self.data == None or self.data == {}
    
    def clear(self):
        self.data = {}

    def update_nested_value(self, keys: List[str], value: Any, overwrite: bool = True) -> bool:
        """
        Update nested value using list of keys
        
        Args:
            keys: List of keys representing the path (e.g., ["a", "b", "c"])
            value: Value to set at the final key
            giveup: If value already exists, whether give up or not
            
        Returns:
            bool: True if old value was empty or same as new value
        """
        if value is None or len(value) == 0:
            return True
        current = self.data
        for key in keys[:-1]:
            current = current.setdefault(key, {})
        if keys[-1] not in current:
            current[keys[-1]] = value
            return True
        elif current[keys[-1]] != value :
            if overwrite: current[keys[-1]] = value
            print(f"\nUpdate contest value to different data, old: {current[keys[-1]]}, new: {value}, overwrite: {overwrite}")
            return False
        else: return True

    def get_nested_value(self, keys: List[str], default: Any = None) -> Any:
        """
        Get nested value using list of keys
        
        Args:
            keys: List of keys representing the path
            default: Default value if path doesn't exist
        
        Returns:
            The value at the specified path or default
        """
        current = self.data
        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default

    def update_problem_value(self, problem_idx: int, keys: List[str], value: Any, overwrite: bool = True) -> bool:
        """
        Update problem data at specified index
        
        Args:
            problem_idx: Index of problem to update
            keys: List of keys representing the path (e.g., ["a", "b", "c"])
            value: Value to set at the final key
            giveup: If value already exists, whether give up or not
        
        Returns:
            bool: True if old value was empty or same as new value
        """
        if value is None or len(value) == 0:
            return True
        if "problems" not in self.data:
            self.data["problems"] = []
            
        # Ensure problems list is large enough
        while len(self.data["problems"]) <= problem_idx:
            self.data["problems"].append({})
            
        if problem_idx >= len(self.data["problems"]):
            return False
        
        current = self.data["problems"][problem_idx]
        if keys[-1] not in current:
            current[keys[-1]] = value
            return True
        elif current[keys[-1]] != value :
            if overwrite: current[keys[-1]] = value
            print(f"Update problem value to different data, old: {current[keys[-1]]}, new: {value}, overwrite: {overwrite}")
            return False
        else: return True

    def add_problem(self, problem_data) -> int:
        """Add a new problem and return its index"""
        if "problems" not in self.data:
            self.data["problems"] = []
        self.data["problems"].append(problem_data)
        return len(self.data["problems"]) - 1
    
    def set_problem(self, problem_idx: int, problem_data) -> bool:
        if "problems" not in self.data:
            self.data["problems"] = []
            
        # Ensure problems list is large enough
        while len(self.data["problems"]) <= problem_idx:
            self.data["problems"].append({})

        if problem_idx >= len(self.data["problems"]):
            return False
            
        self.data["problems"][problem_idx] = problem_data
        return True

    def get_problem(self, problem_idx: int):
        """Get problem data by index or None if doesn't exist"""
        try:
            return self.data["problems"][problem_idx]
        except (KeyError, IndexError):
            return None

    def __str__(self) -> str:
        """Return pretty-printed JSON string"""
        return json.dumps(self.data, indent=4, ensure_ascii=False)

# <Usage>
# # Initialize with file
# handler = JSONHandler("contest_data.json")

# # Initialize contest data
# handler.init_contest_data(["ICPC", "2024"])

# # Add problems
# problem1_idx = handler.add_problem({
#     "id": "A",
#     "title": "Bottles",
#     "solved": 62
# })

# # Update problem
# handler.update_problem(problem1_idx, {
#     "difficulty": "easy",
#     "tags": ["implementation"]
# })

# # Update nested values
# handler.update_nested_value(["metadata", "created_by"], "admin")

# # Save to file
# handler.save()

# # Print current data
# print(handler)