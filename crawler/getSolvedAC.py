import requests

def get_problem_query_json(problem_id):
    """
    Get the query JSON for a problem number from Solved.ac API
    
    Args:
        problem_id (int): The problem number to query
        
    Returns:
        dict: The query JSON response
    """
    url = f"https://solved.ac/api/v3/problem/show"
    params = {
        "problemId": problem_id
    }
    
    headers = {
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()  # Raise exception for HTTP errors
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching problem data: {e}")
        return None

def get_problem_original_name(problem_id):
    """
    Get the original name of a problem from Solved.ac API
    
    Args:
        problem_id (int): The problem number to query
        
    Returns:
        str: The original name of the problem
    """
    query_json = get_problem_query_json(problem_id)
    
    if query_json and 'titles' in query_json:
        titles = query_json['titles']
        for title in titles:
            if title['isOriginal']:
                return title['title']
    return None

# Example usage
if __name__ == "__main__":
    problem_number = 10330  # Example problem number
    query_json = get_problem_query_json(problem_number)
    
    if query_json:
        print("Query JSON for problem", problem_number)
        print(query_json)
    else:
        print("Failed to get query JSON")

    query_name = get_problem_original_name(problem_number)
    if query_name:
        print("Original name for problem", problem_number)
        print(query_name)
    else:
        print("Failed to get original name")