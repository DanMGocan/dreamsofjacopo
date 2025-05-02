"""
Utility functions for subscription management.
"""

def check_downgrade_eligibility(user_id: int, target_tier: int, db):
    """
    Checks if a user is eligible to downgrade to a lower tier based on their current usage.
    
    Args:
        user_id: The user's ID
        target_tier: The tier to downgrade to (0 for Free, 1 for Premium)
        db: Database connection
        
    Returns:
        tuple: (eligible, message) where eligible is a boolean and message explains why if not eligible
    """
    cursor = db.cursor(dictionary=True)
    
    try:
        # Get the number of presentations
        cursor.execute("SELECT COUNT(*) as count FROM pdf WHERE user_id = %s", (user_id,))
        presentation_count = cursor.fetchone()['count']
        
        # Get the maximum number of sets per presentation
        cursor.execute("""
            SELECT p.pdf_id, COUNT(s.set_id) as set_count
            FROM pdf p
            LEFT JOIN `set` s ON p.pdf_id = s.pdf_id
            WHERE p.user_id = %s
            GROUP BY p.pdf_id
            ORDER BY set_count DESC
            LIMIT 1
        """, (user_id,))
        max_sets_result = cursor.fetchone()
        max_sets = max_sets_result['set_count'] if max_sets_result else 0
        
        # Check limits based on target tier
        if target_tier == 0:  # Free tier
            if presentation_count > 1:
                return False, f"You have {presentation_count} presentations. Free tier allows only 1 presentation. Please delete {presentation_count - 1} presentations before downgrading."
            if max_sets > 3:
                return False, f"You have a presentation with {max_sets} sets. Free tier allows only 3 sets per presentation. Please delete some sets before downgrading."
        elif target_tier == 1:  # Premium tier
            if presentation_count > 3:
                return False, f"You have {presentation_count} presentations. Premium tier allows only 3 presentations. Please delete {presentation_count - 3} presentations before downgrading."
            if max_sets > 5:
                return False, f"You have a presentation with {max_sets} sets. Premium tier allows only 5 sets per presentation. Please delete some sets before downgrading."
        
        return True, "Eligible for downgrade"
        
    finally:
        cursor.close()
