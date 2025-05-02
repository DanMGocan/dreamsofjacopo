document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('upgradeForm');
    const totalPriceSpan = document.getElementById('totalPrice');
    const planRadios = document.querySelectorAll('input[name="selected_plan"]');
    
    // Plan prices
    const planPrices = {
        "0": 0,      // Free
        "1": 5.99,   // Premium
        "2": 11.99   // Corporate
    };
    
function calculateTotal() {
    // Calculate base plan price
    let selectedPlan = "0";
    planRadios.forEach(radio => {
        if (radio.checked) {
            selectedPlan = radio.value;
        }
    });
    const total = planPrices[selectedPlan];
    
    // Update display
    totalPriceSpan.textContent = `€${total.toFixed(2)}`;
    
    // Update visual feedback for selected plan
    updateSelectedPlanVisuals(selectedPlan);
}

function updateSelectedPlanVisuals(selectedPlan) {
    // Remove highlighting from all cards
    const allCards = document.querySelectorAll('.card.mb-4');
    allCards.forEach(card => {
        card.classList.remove('border', 'border-success', 'border-3');
        const header = card.querySelector('.card-header');
        if (header) {
            header.classList.remove('bg-success', 'text-white');
        }
        const button = card.querySelector('button');
        if (button) {
            button.classList.remove('btn-success');
            button.classList.add('btn-outline-primary');
            // Remove check icon if present
            const icon = button.querySelector('i.fas.fa-check-circle');
            if (icon) {
                button.innerHTML = 'Select Plan';
            }
        }
    });
    
    // Add highlighting to the selected card
    const selectedCard = document.getElementById(`${getPlanName(selectedPlan)}Plan`).closest('.card');
    selectedCard.classList.add('border', 'border-success', 'border-3');
    const selectedHeader = selectedCard.querySelector('.card-header');
    if (selectedHeader) {
        selectedHeader.classList.add('bg-success', 'text-white');
    }
    const selectedButton = selectedCard.querySelector('button');
    if (selectedButton) {
        selectedButton.classList.remove('btn-outline-primary');
        selectedButton.classList.add('btn-success');
        selectedButton.innerHTML = '<i class="fas fa-check-circle me-2"></i>Current Plan';
    }
}

function getPlanName(planValue) {
    switch(planValue) {
        case "0": return "free";
        case "1": return "premium";
        case "2": return "corporate";
        default: return "free";
    }
}
    
    // Add event listeners
    planRadios.forEach(radio => {
        radio.addEventListener('change', calculateTotal);
    });
    
    // Initial calculation
    calculateTotal();
    
    // Make these functions available globally
    window.calculateTotal = calculateTotal;
    window.selectPlan = function(planValue) {
        // Check the radio button
        const radio = document.getElementById(`${getPlanName(planValue)}Plan`);
        if (radio) {
            radio.checked = true;
            
            // Update the total and visuals
            calculateTotal();
        }
    };
});
