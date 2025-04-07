document.addEventListener('DOMContentLoaded', function() {
  fetch('./gridData.json')
    .then(response => response.json())
    .then(data => {
      const grid = document.getElementById('grid');
      // Create 5x5 grid
      for (let row = 0; row < 5; row++) {
        const tr = document.createElement('tr');
        for (let col = 0; col < 5; col++) {
          const cell = document.createElement('td');
          const cellData = data.find(item => item.row === row && item.col === col);
          
          // Set cell properties
          cell.textContent = cellData?.value || '';
          cell.dataset.state = cellData?.state || 0;
          cell.style.backgroundColor = 
            cell.dataset.state === '0' ? '#ffcccc' :
            cell.dataset.state === '1' ? '#ccffcc' : '#ccccff';
          cell.style.border = '2px solid #555';
          cell.style.padding = '20px';
          cell.style.cursor = 'pointer';
          
          // Click handler
          cell.addEventListener('click', function() {
            const newState = (parseInt(this.dataset.state) + 1) % 3;
            this.dataset.state = newState;
            this.style.backgroundColor = 
              newState === 0 ? '#ffcccc' :
              newState === 1 ? '#ccffcc' : '#ccccff';
          });
          
          tr.appendChild(cell);
        }
        grid.appendChild(tr);
      }
    });
});