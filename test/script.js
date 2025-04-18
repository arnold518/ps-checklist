// Sample data
const elementStates = [0, 1, 2, 3, 0, 0, 1, 2, 3, 3, 3, 1, 2, 0, 1];
const stateNames = {
  0: "Not Started",
  1: "In Progress",
  2: "Needs Review",
  3: "Completed"
};

function updateProgressBar(states) {
  const totalElements = states.length;
  if (totalElements === 0) return;
  
  const stateCounts = [0, 0, 0, 0];
  states.forEach(state => {
    if (state >= 0 && state <= 3) stateCounts[state]++;
  });
  
  const progressBar = document.getElementById('progressBar');
  const hoverBox = document.getElementById('hoverBox');
  progressBar.innerHTML = '';
  
  stateCounts.forEach((count, state) => {
    if (count > 0) {
      const percentage = (count / totalElements) * 100;
      const segment = document.createElement('div');
      segment.className = `progress-segment state-${state}`;
      segment.style.width = `${percentage}%`;
      segment.dataset.state = state;
      segment.dataset.count = count;
      segment.dataset.total = totalElements;
      
      // Only show count if segment is wide enough
      if (percentage > 15) {
        segment.textContent = `${count}`;
      }
      
      // Mouse enter event
      segment.addEventListener('mousemove', (e) => {
        const percentage = (count / totalElements * 100).toFixed(1);
        hoverBox.innerHTML = `
          <div><strong>${stateNames[state]}</strong></div>
          <div>Elements: ${count}/${totalElements}</div>
          <div>Percentage: ${percentage}%</div>
        `;
        hoverBox.classList.add('show');
        
        // Position the hover box near the mouse
        const x = e.clientX;
        const y = e.clientY;
        hoverBox.style.left = `${x}px`;
        hoverBox.style.top = `${y}px`;
      });
      
      // Mouse leave event
      segment.addEventListener('mouseleave', () => {
        hoverBox.classList.remove('show');
      });
      
      progressBar.appendChild(segment);
    }
  });
}

// Initialize
updateProgressBar(elementStates);

// Make hover box follow mouse when moving over the progress bar
document.getElementById('progressBar').addEventListener('mousemove', (e) => {
  const hoverBox = document.getElementById('hoverBox');
  if (hoverBox.classList.contains('show')) {
    hoverBox.style.left = `${e.clientX}px`;
    hoverBox.style.top = `${e.clientY}px`;
  }
});