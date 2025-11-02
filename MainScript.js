const API_BASE = 'http://localhost:5000';

let transcriptsFolder = { handle: null, name: '', path: '' };
let uploadedCSVFile = null;

// Global store for all successful projects (Used by the dropdown)
let allChatProjects = []; 

// Global variables for the new chat summary table logic
let currentChatData = [];
let currentSortColumn = 'Volume';
let currentSortDirection = 'desc';


/* === 1. CORE UI STATE MANAGEMENT === */

/**
 * Handles switching between different application views (Admin, Chat, Home).
 */
function showView(viewName) {
    const createButtonContainer = document.getElementById('createProjectButtonContainer');
    const resultsPanel = document.getElementById('resultsPanel');
    const landingMain = document.querySelector('.landing-main');
    const chatProjectSelector = document.getElementById('chatProjectSelectorContainer'); 
    
    let missingElement = null;
    if (!createButtonContainer) missingElement = 'createProjectButtonContainer';
    if (!resultsPanel) missingElement = 'resultsPanel';
    if (!landingMain) missingElement = 'landingMain (class: .landing-main)';
    if (!chatProjectSelector) missingElement = 'chatProjectSelectorContainer';

    if (missingElement) { 
        console.error(`CRITICAL ERROR: The element with ID/Class "${missingElement}" was not found by JavaScript. Navigation failed.`);
        return;
    }

    // 1. Reset state: Hide all view containers and UI controls
    resultsPanel.style.display = 'none';
    
    // Clear or hide temporary content container (but keep resultsPanel in DOM)
    const tempContent = document.getElementById('temporaryViewContent');
    if (tempContent) {
        tempContent.remove();
    }
    
    // Reset specific header elements for a clean slate
    createButtonContainer.style.display = 'none';
    chatProjectSelector.style.display = 'none';


    // 2. Apply view-specific logic
    if (viewName === 'admin') {
        console.log("Switching to ADMIN view...");
        
        // SHOW: Create Project button
        createButtonContainer.style.display = 'block'; 
        
        // SHOW: Results Table Panel
        resultsPanel.style.display = 'block';
        
        loadProjectsToTable(); 
        
    } else if (viewName === 'chat') {
        console.log("Switching to CHAT view...");
        
        // SHOW: The Chat Project Selector dropdown
        chatProjectSelector.style.display = 'flex'; 
        
        loadProjectsToChatDropdown(); 
        
        // Create temporary view content AFTER resultsPanel
        const tempDiv = document.createElement('div');
        tempDiv.id = 'temporaryViewContent';
        tempDiv.style.cssText = 'text-align: center;';
        tempDiv.innerHTML = '<img src="assets/img/TranscripttoChatBkrnd.png" alt="Home" class="bkrnd-icon-size" />';
        landingMain.appendChild(tempDiv);
    
    } else if (viewName === 'home') {
        console.log("Switching to HOME view...");
        
        // Create temporary view content AFTER resultsPanel
        const tempDiv = document.createElement('div');
        tempDiv.id = 'temporaryViewContent';
        tempDiv.style.cssText = 'text-align: center;';
        tempDiv.innerHTML = '<img src="assets/img/TranscripttoChatBkrnd.png" alt="Home" class="bkrnd-icon-size" />';
        landingMain.appendChild(tempDiv);
    }
}


/* === 2. API & PROJECT CREATION/LOADING (ADMIN VIEW) === */

function openCreateProject() {
  const panel = document.getElementById('createProjectPanel');
  if (!panel) return;
  panel.classList.remove('hidden');
  panel.classList.add('is-open');
  panel.setAttribute('aria-hidden', 'false');
}

function closeCreateProject() {
  const panel = document.getElementById('createProjectPanel');
  if (!panel) return;
  panel.classList.remove('is-open');
  setTimeout(() => {
    panel.classList.add('hidden');
    panel.setAttribute('aria-hidden', 'true');
  }, 500);
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const panel = document.getElementById('createProjectPanel');
    if (panel && panel.classList.contains('is-open')) {
      closeCreateProject();
    }
  }
});

async function handleSaveProject() {
  console.log('Save button clicked');
  
  const projectName = document.querySelector('[name="projectName"]').value.trim();
  const projectDescription = document.querySelector('[name="projectDescription"]').value.trim();
  
  if (!projectName || !uploadedCSVFile) {
    alert('Please enter a project name and upload a CSV file.');
    return;
  }
  
  const saveButton = document.querySelector('.ngnx-footer-button.ngnx-button--primary');
  const originalText = saveButton.querySelector('.ngnx-button__label').textContent;
  saveButton.querySelector('.ngnx-button__label').textContent = 'Creating...';
  saveButton.disabled = true;
  
  try {
    const formData = new FormData();
    formData.append('projectName', projectName);
    formData.append('projectDescription', projectDescription);
    formData.append('csv_file', uploadedCSVFile);
    
    const response = await fetch(`${API_BASE}/api/projects`, {
      method: 'POST',
      body: formData
    });
    
    const result = await response.json();
    
    if (result.success) {
      addProjectToTable({
        id: result.project_id,
        name: projectName,
        csv_filename: uploadedCSVFile.name,
        total_records: result.stats.valid_rows,
        created_at: new Date().toISOString()
      }, true);
      
      closeCreateProject();
      document.querySelector('[name="projectName"]').value = '';
      document.querySelector('[name="projectDescription"]').value = '';
      document.getElementById('fileDropRef').value = '';
      uploadedCSVFile = null;
      document.querySelector('.drag-file-label').innerHTML = 'Drag files here or <span>Browse</span>';
      
    } else {
      addFailedResultToTable({
        projectName: projectName,
        fileName: uploadedCSVFile.name,
        errors: result.errors || []
      });
    }
    
  } catch (error) {
    console.error('Network error:', error);
    addFailedResultToTable({
      projectName: projectName,
      fileName: uploadedCSVFile.name,
      errors: ['Failed to connect to server. Make sure Flask backend is running.']
    });
  } finally {
    saveButton.querySelector('.ngnx-button__label').textContent = originalText;
    saveButton.disabled = false;
  }
}

function createResultsTable() {
  const panelBody = document.querySelector('.ngnx-main-panel__body');
  if (!panelBody) return;
  panelBody.innerHTML = `
    <table class="results-table">
      <thead class="results-table-head">
        <tr>
          <th>PROJECT NAME</th>
          <th>PROGRESS</th>
          <th>FILE NAME</th>
          <th>CREATION DATE</th>
          <th>COMMENT</th>
          <th class="delete-header">DELETE</th>
        </tr>
      </thead>
      <tbody class="results-table-body">
      </tbody>
    </table>
  `;
}

function addProjectToTable(project, prepend = true) {
  let tbody = document.querySelector('.ngnx-main-panel__body .results-table-body');
  if (!tbody) {
    createResultsTable();
    tbody = document.querySelector('.ngnx-main-panel__body .results-table-body');
  }
  
  if (!tbody) return;
  
  const createdDate = new Date(project.created_at).toLocaleString();
  const comment = `✅ ${project.total_records || 0} records`;
  
  const row = document.createElement('tr');
  row.setAttribute('data-project-id', project.id);
  row.innerHTML = `
    <td>${project.name}</td>
    <td><span class="status-badge status-success">Successful</span></td>
    <td>${project.csv_filename || 'N/A'}</td>
    <td>${createdDate}</td>
    <td class="comment-cell">${comment}</td>
    <td class="delete-cell">
      <button class="delete-btn" onclick="deleteProject(${project.id})" title="Delete project">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="3 6 5 6 21 6"></polyline>
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
          <line x1="10" y1="11" x2="10" y2="17"></line>
          <line x1="14" y1="11" x2="14" y2="17"></line>
        </svg>
      </button>
    </td>
  `;
  
  if (prepend) {
    tbody.insertBefore(row, tbody.firstChild);
  } else {
    tbody.appendChild(row);
  }
  
  document.querySelector('.ngnx-xo-results__panel').style.display = 'block';
}

function addFailedResultToTable(result) {
  let tbody = document.querySelector('.ngnx-main-panel__body .results-table-body');
  if (!tbody) {
    createResultsTable();
    tbody = document.querySelector('.ngnx-main-panel__body .results-table-body');
  }

  const now = new Date().toLocaleString();
  const comment = result.errors?.join('; ') || 'Unknown error';
  
  const row = document.createElement('tr');
  row.innerHTML = `
    <td>${result.projectName}</td>
    <td><span class="status-badge status-failed">Failed</span></td>
    <td>${result.fileName}</td>
    <td>${now}</td>
    <td class="comment-cell">${comment}</td>
    <td class="delete-cell">
      <button class="delete-btn-disabled" disabled title="Cannot delete failed uploads">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" opacity="0.3">
          <polyline points="3 6 5 6 21 6"></polyline>
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
          <line x1="10" y1="11" x2="10" y2="17"></line>
          <line x1="14" y1="11" x2="14" y2="17"></line>
        </svg>
      </button>
    </td>
  `;
  tbody.insertBefore(row, tbody.firstChild);
  document.querySelector('.ngnx-xo-results__panel').style.display = 'block';
}

async function loadProjectsToTable() {
  try {
    const response = await fetch(`${API_BASE}/api/projects`);
    const result = await response.json();
    
    if (result.success && result.projects) {
      createResultsTable();
      const sortedProjects = result.projects.sort((a, b) => b.id - a.id);
      sortedProjects.forEach(project => {
        if (project.total_records > 0) {
            addProjectToTable(project, false);
        }
      });
    }
  } catch (error) {
    console.error('Failed to load projects to Admin table:', error);
  }
}

async function deleteProject(projectId) {
  if (!confirm('Are you sure you want to delete this project? This action cannot be undone.')) {
    return;
  }
  
  try {
    const response = await fetch(`${API_BASE}/api/projects/${projectId}`, {
      method: 'DELETE'
    });
    
    const result = await response.json();
    
    if (result.success) {
      const row = document.querySelector(`tr[data-project-id="${projectId}"]`);
      if (row) row.remove();
      
      const tbody = document.querySelector('.results-table-body');
      if (tbody && tbody.children.length === 0) {
        document.querySelector('.ngnx-xo-results__panel').style.display = 'none';
      }
      console.log('Project deleted successfully');
    } else {
      alert('Failed to delete project: ' + result.error);
    }
  } catch (error) {
    console.error('Error deleting project:', error);
    alert('Failed to delete project. Please try again.');
  }
}

async function testAPIConnection() {
  try {
    const response = await fetch(`${API_BASE}/api/health`);
    const result = await response.json();
    if (result.status === 'healthy') {
      console.log('✅ API connection successful!');
      return true;
    }
  } catch (error) {
    console.error('❌ API connection failed. Make sure Flask backend is running.');
    return false;
  }
}

/* === 3. CHAT DROPDOWN LOGIC === */

async function loadProjectsToChatDropdown() {
    try {
        const response = await fetch(`${API_BASE}/api/projects`);
        const result = await response.json();
        const dropdownList = document.getElementById('chatProjectDropdown');
        
        if (result.success && result.projects) {
            const successfulProjects = result.projects.filter(p => p.total_records > 0);
            successfulProjects.sort((a, b) => a.name.localeCompare(b.name));
            allChatProjects = successfulProjects;
            dropdownList.innerHTML = '';
            
            if (successfulProjects.length === 0) {
                dropdownList.innerHTML = '<li class="no-results">No completed projects available.</li>';
            } else {
                successfulProjects.forEach(project => {
                    const li = document.createElement('li');
                    li.textContent = project.name;
                    li.setAttribute('data-project-id', project.id);
                    li.onclick = () => selectChatProject(project.id, project.name);
                    dropdownList.appendChild(li);
                });
            }
            setupChatDropdownEvents();
        }
    } catch (error) {
        console.error('Failed to load projects for chat dropdown:', error);
        document.getElementById('chatProjectDropdown').innerHTML = '<li class="no-results" style="color:red;">Error loading projects.</li>';
    }
}

function setupChatDropdownEvents() {
    const input = document.getElementById('chatProjectSearch');
    const dropdownList = document.getElementById('chatProjectDropdown');
    const arrow = document.getElementById('chatDropdownArrow'); 

    const showDropdown = () => {
        dropdownList.classList.remove('hidden');
        arrow.classList.add('open'); 
        input.setAttribute('aria-expanded', 'true');
    };
    
    const hideDropdown = () => {
        dropdownList.classList.add('hidden');
        arrow.classList.remove('open'); 
        input.setAttribute('aria-expanded', 'false');
    };

    input.onfocus = showDropdown;
    input.onclick = (e) => {
        e.stopPropagation();
        if (dropdownList.classList.contains('hidden')) {
            showDropdown();
        } else {
            hideDropdown();
        }
    };

    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !dropdownList.contains(e.target) && !arrow.contains(e.target)) {
            hideDropdown(); 
        }
    });

    input.oninput = (e) => {
        const searchText = e.target.value.toLowerCase();
        const items = dropdownList.querySelectorAll('li:not(.no-results-message)');
        let visibleCount = 0;
        
        items.forEach(li => {
            const projectName = li.textContent.toLowerCase();
            if (projectName.includes(searchText)) {
                li.style.display = 'block';
                visibleCount++;
            } else {
                li.style.display = 'none';
            }
        });
        
        let noResultsLi = dropdownList.querySelector('.no-results-message');
        if (!noResultsLi) {
            noResultsLi = document.createElement('li');
            noResultsLi.className = 'no-results no-results-message';
            noResultsLi.textContent = 'No matching projects.';
            dropdownList.appendChild(noResultsLi);
        }
        noResultsLi.style.display = (visibleCount === 0) ? 'block' : 'none';
        
        showDropdown();
    };
}


/* === 4. CHAT SUMMARY TABLE LOGIC (NEW FEATURE) === */

/**
 * Handles project selection from the dropdown and initiates data fetch.
 * @param {number} projectId 
 * @param {string} projectName 
 */
function selectChatProject(projectId, projectName) {
    const input = document.getElementById('chatProjectSearch');
    const dropdownList = document.getElementById('chatProjectDropdown');

    input.value = projectName;
    input.setAttribute('data-selected-id', projectId);
    dropdownList.classList.add('hidden');
    document.getElementById('chatDropdownArrow')?.classList.remove('open');
    
    console.log(`Project selected for chat: ID ${projectId}, Name ${projectName}`);
    
    fetchAndDisplayProjectSummary(projectId, projectName);
}

/**
 * Fetches the summarized data for a selected project and calls the table generator.
 */
async function fetchAndDisplayProjectSummary(projectId, projectName) {
    const landingMain = document.querySelector('.landing-main');
    
    // Remove any existing temporary content (no loading message)
    const tempContent = document.getElementById('temporaryViewContent');
    if (tempContent) {
        tempContent.remove();
    }

    try {
        const response = await fetch(`${API_BASE}/api/projects/${projectId}/summary`);
        
        if (!response.ok) {
             throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const summaryData = await response.json(); 

        if (summaryData.success && summaryData.summary) {
            // Data is fetched successfully, create the table
            createChatSummaryTable(summaryData.summary, projectName);
        } else {
            // Handle case where project exists but has no data
            createChatSummaryTable([], projectName, summaryData.message || 'No summary data returned.');
        }

    } catch (error) {
        console.error('Error fetching project summary:', error);
        
        const landingMain = document.querySelector('.landing-main');
        
        // Remove temporary content if it exists
        const tempContent = document.getElementById('temporaryViewContent');
        if (tempContent) {
            tempContent.remove();
        }
        
        const errorDiv = document.createElement('div');
        errorDiv.id = 'temporaryViewContent';
        errorDiv.style.cssText = 'text-align: center; padding: 50px;';
        errorDiv.innerHTML = `
            <h2 style="color: red;">Error Loading Summary</h2>
            <p>Failed to load data for project: ${projectName}. Check console for details. Ensure backend is running and the new '/summary' endpoint is defined.</p>
            <p>Error details: ${error.message}</p>
        `;
        landingMain.appendChild(errorDiv);
    }
}

/**
 * Generates and displays the sortable/reorganizable table.
 */
function createChatSummaryTable(data, projectName, message = null) {
    const landingMain = document.querySelector('.landing-main');
    currentChatData = data; // Store data globally for sorting
    currentSortColumn = 'Volume';
    currentSortDirection = 'desc';
    
    // Define the columns: Category, Topic, Intent, Agent Task, Volume, AI Chat
    const columnDefinitions = [
        { key: 'Category', label: 'Category', sortable: true },
        { key: 'Topic', label: 'Topic', sortable: true },
        { key: 'Intent', label: 'Intent', sortable: true },
        { key: 'Agent_Task', label: 'Agent Task', sortable: true },
        { key: 'Volume', label: 'Volume', sortable: true, type: 'number' },
        { key: 'AI_Chat', label: 'AI Chat', sortable: false, isIcon: true }
    ];
    
    const generateTableHTML = (data, columns, headerKeys) => {
        const keys = headerKeys || columns.map(c => c.key);
        
        const headerRow = keys.map(key => {
            const col = columns.find(c => c.key === key);
            if (!col) return ''; 
            const isSortable = col.sortable ? 'sortable-column' : '';
            // AI Chat icon column gets smaller width
            const flexStyle = col.isIcon ? 'flex: 0 0 100px;' : 'flex: 1;';
            return `
                <th data-key="${col.key}" data-type="${col.type || 'string'}" 
                    class="${isSortable} chat-table-header"
                    ${col.sortable ? `onclick="handleChatTableSort('${col.key}')"` : ''}
                    draggable="true"
                    style="${flexStyle} min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    ${col.label}
                    <span class="sort-icon ${col.key === currentSortColumn ? currentSortDirection : ''}"></span>
                </th>
            `;
        }).join('');

        const bodyRows = data.map(row => {
            const rowCells = keys.map(key => {
                const col = columns.find(c => c.key === key);
                // AI Chat icon column gets smaller width
                const flexStyle = col && col.isIcon ? 'flex: 0 0 100px;' : 'flex: 1;';
                // Special handling for AI Chat icon column
                if (col && col.isIcon) {
                    return `<td style="${flexStyle} text-align: center; min-width: 0;"><img src="assets/img/bot-builder.svg" alt="Chat" style="width: 24px; height: 24px; cursor: pointer;" onclick="openAIChat('${row.Intent}', '${row.Topic}')"/></td>`;
                }
                return `<td title="${row[key] || 'N/A'}" style="${flexStyle} min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${row[key] || 'N/A'}</td>`;
            }).join('');
            return `<tr style="display: flex; width: 100%;">${rowCells}</tr>`;
        }).join('');

        return `
            <div class="table-wrapper" style="width: 100%; height: 100%; display: flex; flex-direction: column; overflow: hidden;">
                <table id="chatSummaryTable" class="ngnx-xo-summary-table" style="width: 100%; display: flex; flex-direction: column; flex: 1; overflow: hidden;">
                    <thead id="chatSummaryTableHead" style="display: block; width: 100%;">
                        <tr style="display: flex; width: 100%;">${headerRow}</tr>
                    </thead>
                    <tbody id="chatSummaryTableBody" style="display: block; flex: 1; overflow-y: auto; overflow-x: hidden; width: 100%;">${bodyRows || '<tr style="display: flex; width: 100%;"><td colspan="' + columns.length + '" style="text-align: center; color: #999; padding: 30px; flex: 1;">' + (message || 'No data found for this project.') + '</td></tr>'}</tbody>
                </table>
            </div>
        `;
    };
    
    // 1. Sort initial data by Volume DESC
    data.sort((a, b) => b.Volume - a.Volume);
    
    // 2. Remove any existing temporary content
    const tempContent = document.getElementById('temporaryViewContent');
    if (tempContent) {
        tempContent.remove();
    }
    
    // 3. Create and append new content container (100% width and height, no page scroll)
    const contentDiv = document.createElement('div');
    contentDiv.id = 'temporaryViewContent';
    contentDiv.style.cssText = 'width: 100%; height: 100%; overflow: hidden; display: flex; flex-direction: column;';
    contentDiv.innerHTML = `
        <div class="chat-summary-table-container" style="width: 100%; height: 100%; overflow: hidden; display: flex; flex-direction: column;">
            ${generateTableHTML(data, columnDefinitions)}
        </div>
    `;
    landingMain.appendChild(contentDiv);
    
    // 4. Attach drag/drop handlers
    if (data.length > 0) {
        attachChatTableDragDropHandlers();
    }
}


/**
 * Sorting logic for the summary table.
 */
function handleChatTableSort(key) {
    if (currentChatData.length === 0) return;
    
    let direction = currentSortDirection;
    
    // Toggle direction if clicking the same column
    if (key === currentSortColumn) {
        direction = direction === 'asc' ? 'desc' : 'asc';
    } else {
        // Default to descending for new column, especially Volume
        direction = key === 'Volume' ? 'desc' : 'asc'; 
        currentSortColumn = key;
    }
    
    currentSortDirection = direction;
    
    // Get column type from DOM
    const headerElement = document.querySelector(`th[data-key="${key}"]`);
    const columnType = headerElement ? headerElement.getAttribute('data-type') : 'string';
    
    // Perform sort
    currentChatData.sort((a, b) => {
        const valA = a[key];
        const valB = b[key];
        
        if (columnType === 'number') {
            return direction === 'asc' ? valA - valB : valB - valA;
        } else {
            const strA = String(valA).toLowerCase();
            const strB = String(valB).toLowerCase();
            
            if (strA < strB) return direction === 'asc' ? -1 : 1;
            if (strA > strB) return direction === 'asc' ? 1 : -1;
            return 0;
        }
    });
    
    // Re-render the table body
    updateChatTableBody();
}

/**
 * Re-renders the table body after a sort or drag/drop operation.
 */
function updateChatTableBody() {
    const tbody = document.getElementById('chatSummaryTableBody');
    if (!tbody || currentChatData.length === 0) return;
    
    // Get current column order from the DOM
    const headerKeys = Array.from(document.querySelectorAll('#chatSummaryTableHead th')).map(th => th.getAttribute('data-key'));
    
    // Column definitions for reference (to check for icon columns)
    const columnDefinitions = [
        { key: 'Category', label: 'Category', sortable: true },
        { key: 'Topic', label: 'Topic', sortable: true },
        { key: 'Intent', label: 'Intent', sortable: true },
        { key: 'Agent_Task', label: 'Agent Task', sortable: true },
        { key: 'Volume', label: 'Volume', sortable: true, type: 'number' },
        { key: 'AI_Chat', label: 'AI Chat', sortable: false, isIcon: true }
    ];
    
    // Rebuild rows based on sorted data and current column order
    const bodyRows = currentChatData.map(row => {
        const rowCells = headerKeys.map(key => {
            const col = columnDefinitions.find(c => c.key === key);
            const flexStyle = col && col.isIcon ? 'flex: 0 0 100px;' : 'flex: 1;';
            
            // Special handling for AI Chat icon column
            if (col && col.isIcon) {
                return `<td style="${flexStyle} text-align: center; min-width: 0;"><img src="assets/img/bot-builder.svg" alt="Chat" style="width: 24px; height: 24px; cursor: pointer;" onclick="openAIChat('${row.Intent}', '${row.Topic}')"/></td>`;
            }
            return `<td title="${row[key] || 'N/A'}" style="${flexStyle} min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${row[key] || 'N/A'}</td>`;
        }).join('');
        return `<tr style="display: flex; width: 100%;">${rowCells}</tr>`;
    }).join('');
    
    tbody.innerHTML = bodyRows;
    
    // Update sort icons in the header
    document.querySelectorAll('.sortable-column').forEach(th => {
        const icon = th.querySelector('.sort-icon');
        icon.className = 'sort-icon'; // Reset class
        
        if (th.getAttribute('data-key') === currentSortColumn) {
            icon.classList.add(currentSortDirection);
        }
    });
}

/**
 * Implements pure JavaScript column drag-and-drop for the table.
 */
function attachChatTableDragDropHandlers() {
    const tableHeadRow = document.querySelector('#chatSummaryTableHead tr');
    if (!tableHeadRow) return;
    
    let dragColumn = null;

    const startDrag = (e) => {
        dragColumn = e.target.closest('th');
        if (!dragColumn || dragColumn.getAttribute('draggable') !== 'true') return;
        
        dragColumn.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', dragColumn.getAttribute('data-key')); 
    };

    const dragOver = (e) => {
        e.preventDefault();
        const targetColumn = e.target.closest('th');
        if (targetColumn && targetColumn !== dragColumn) {
            tableHeadRow.querySelectorAll('th').forEach(th => th.classList.remove('drag-over-left', 'drag-over-right'));
            
            const rect = targetColumn.getBoundingClientRect();
            if (e.clientX < rect.left + rect.width / 2) {
                targetColumn.classList.add('drag-over-left');
            } else {
                targetColumn.classList.add('drag-over-right');
            }
        }
    };

    const dropColumn = (e) => {
        e.preventDefault();
        const dropTarget = e.target.closest('th');
        if (!dragColumn || !dropTarget || dragColumn === dropTarget) {
            tableHeadRow.querySelectorAll('th').forEach(th => th.classList.remove('dragging', 'drag-over-left', 'drag-over-right'));
            return;
        }

        const rect = dropTarget.getBoundingClientRect();
        const insertBefore = e.clientX < rect.left + rect.width / 2;

        if (insertBefore) {
            tableHeadRow.insertBefore(dragColumn, dropTarget);
        } else {
            tableHeadRow.insertBefore(dragColumn, dropTarget.nextSibling);
        }
        
        tableHeadRow.querySelectorAll('th').forEach(th => th.classList.remove('dragging', 'drag-over-left', 'drag-over-right'));

        // Re-render the body rows to match the new header order
        updateChatTableBody();
    };
    
    const dragEnd = (e) => {
        e.target.closest('th')?.classList.remove('dragging');
        tableHeadRow.querySelectorAll('th').forEach(th => th.classList.remove('drag-over-left', 'drag-over-right'));
    };
    
    // Apply drag handlers to all header columns
    tableHeadRow.querySelectorAll('th').forEach(th => {
        th.addEventListener('dragstart', startDrag);
        th.addEventListener('dragover', dragOver);
        th.addEventListener('drop', dropColumn);
        th.addEventListener('dragend', dragEnd);
    });
}


/**
 * Handler for AI Chat icon click
 * Opens AI chat interface for the selected intent/topic
 */
function openAIChat(intent, topic) {
    console.log('Opening AI Chat for:', { intent, topic });
    // TODO: Implement AI chat functionality
    // For now, just show an alert
    alert(`AI Chat feature coming soon!\n\nIntent: ${intent}\nTopic: ${topic}`);
}


/* === 5. INITIALIZATION BLOCK === */

document.addEventListener('DOMContentLoaded', () => {
    console.log('=== Application Initializing ===');
    
    testAPIConnection();
    showView('home'); 
    
    const fileInput = document.getElementById('fileDropRef');
    if (fileInput) {
        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file && file.name.endsWith('.csv')) {
                uploadedCSVFile = file;
                const fileLabel = document.querySelector('.drag-file-label');
                if (fileLabel) {
                    fileLabel.innerHTML = `Selected: <strong>${file.name}</strong> (${(file.size / 1024).toFixed(1)} KB)`;
                }
            } else if (file) {
                alert('Please select a CSV file');
            }
        });
    }
    
    const saveButton = document.querySelector('.ngnx-footer-button.ngnx-button--primary');
    if (saveButton) {
        saveButton.addEventListener('click', handleSaveProject);
    }
});