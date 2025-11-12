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
    const filterButtonContainer = document.getElementById('filterProjectButtonContainer');
    const resultsPanel = document.getElementById('resultsPanel');
    const landingMain = document.querySelector('.landing-main');
    const chatProjectSelector = document.getElementById('chatProjectSelectorContainer');

    let missingElement = null;
    if (!createButtonContainer) missingElement = 'createProjectButtonContainer';
    if (!filterButtonContainer) missingElement = 'filterProjectButtonContainer';
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
    filterButtonContainer.style.display = 'none';
    chatProjectSelector.style.display = 'none';


    // 2. Apply view-specific logic
    if (viewName === 'admin') {
        console.log("Switching to ADMIN view...");

        // SHOW: Create Project button
        createButtonContainer.style.display = 'block';

        // HIDE: Filter button (not shown in admin view)
        filterButtonContainer.style.display = 'none';

        // SHOW: Results Table Panel
        resultsPanel.style.display = 'block';

        loadProjectsToTable();

    } else if (viewName === 'chat') {
        console.log("Switching to CHAT view...");

        // SHOW: The Chat Project Selector dropdown
        chatProjectSelector.style.display = 'flex';

        // SHOW: Filter button
        filterButtonContainer.style.display = 'block';

        loadProjectsToChatDropdown();

        // Create temporary view content AFTER resultsPanel
        const tempDiv = document.createElement('div');
        tempDiv.id = 'temporaryViewContent';
        tempDiv.style.cssText = 'text-align: center;';
        tempDiv.innerHTML = '<img src="assets/img/TranscripttoChatBkrnd.png" alt="Home" class="bkrnd-icon-size" />';
        landingMain.appendChild(tempDiv);

    } else if (viewName === 'home') {
        console.log("Switching to HOME view...");

        // SHOW: Filter button
        filterButtonContainer.style.display = 'block';

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

  // Clear old data when opening the panel
  document.querySelector('[name="projectName"]').value = '';
  document.querySelector('[name="projectDescription"]').value = '';
  document.getElementById('fileDropRef').value = '';
  uploadedCSVFile = null;
  document.querySelector('.drag-file-label').innerHTML = 'Drag files here or <span>Browse</span>';

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

// Global state for filter values
let filterValues = {
  categories: [],
  topics: [],
  intents: [],
  agent_tasks: []
};

let selectedFilters = {
  category: [],
  topic: [],
  intent: [],
  agentTask: [],
  isAutomatable: false,
  sentimentMin: null,
  sentimentMax: null,
  durationMin: null,
  durationMax: null
};

// Global sentiment slider instance
let sentimentSlider = null;

// Global duration slider instance
let durationSlider = null;

// Global state for column visibility
const availableColumns = [
  { key: 'Category', label: 'Category' },
  { key: 'Topic', label: 'Topic' },
  { key: 'Intent', label: 'Intent' },
  { key: 'Agent_Task', label: 'Agent Task' }
];

let visibleColumns = {
  Category: true,
  Topic: true,
  Intent: true,
  Agent_Task: false
};

async function openFilterPanel() {
  const panel = document.getElementById('filterPanel');
  if (!panel) return;

  // Get current project ID
  const projectIdInput = document.getElementById('chatProjectSearch');
  const projectId = projectIdInput ? projectIdInput.getAttribute('data-selected-id') : null;

  if (!projectId) {
    alert('Please select a project first');
    return;
  }

  // Load filter values from backend
  try {
    const response = await fetch(`${API_BASE}/api/projects/${projectId}/filter-values`);
    const result = await response.json();

    if (result.success) {
      filterValues = {
        categories: result.filter_values.categories || [],
        topics: result.filter_values.topics || [],
        intents: result.filter_values.intents || [],
        agent_tasks: result.filter_values.agent_tasks || []
      };

      // Populate dropdowns
      populateFilterDropdown('category', filterValues.categories);
      populateFilterDropdown('topic', filterValues.topics);
      populateFilterDropdown('intent', filterValues.intents);
      populateFilterDropdown('agentTask', filterValues.agent_tasks);
    }
  } catch (error) {
    console.error('Error loading filter values:', error);
  }

  // Populate column visibility dropdown
  populateColumnVisibilityDropdown();

  // Initialize sentiment slider
  initializeSentimentSlider(projectId);

  // Initialize duration slider
  initializeDurationSlider(projectId);

  panel.classList.remove('hidden');
  panel.classList.add('is-open');
  panel.setAttribute('aria-hidden', 'false');
}

function closeFilterPanel() {
  const panel = document.getElementById('filterPanel');
  if (!panel) return;
  panel.classList.remove('is-open');
  setTimeout(() => {
    panel.classList.add('hidden');
    panel.setAttribute('aria-hidden', 'true');
  }, 500);
}

function populateFilterDropdown(filterName, values) {
  const optionsContainer = document.getElementById(`${filterName}Options`);
  if (!optionsContainer) return;

  optionsContainer.innerHTML = '';

  values.forEach(value => {
    const optionDiv = document.createElement('div');
    optionDiv.className = 'filter-dropdown-option';
    optionDiv.setAttribute('data-value', value);

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = `${filterName}_${value.replace(/\s+/g, '_')}`;
    checkbox.value = value;
    checkbox.checked = selectedFilters[filterName].includes(value);
    checkbox.onchange = () => toggleFilterSelection(filterName, value);

    const label = document.createElement('label');
    label.htmlFor = checkbox.id;
    label.textContent = value;

    optionDiv.appendChild(checkbox);
    optionDiv.appendChild(label);
    optionsContainer.appendChild(optionDiv);
  });
}

function showFilterDropdown(filterName) {
  const dropdown = document.getElementById(`${filterName}Dropdown`);
  if (dropdown) {
    dropdown.classList.remove('hidden');
  }
}

function filterDropdownOptions(filterName) {
  const searchInput = document.getElementById(`${filterName}SearchInput`);
  const optionsContainer = document.getElementById(`${filterName}Options`);

  if (!searchInput || !optionsContainer) return;

  const searchText = searchInput.value.toLowerCase();
  const options = optionsContainer.querySelectorAll('.filter-dropdown-option');

  options.forEach(option => {
    const label = option.querySelector('label');
    const text = label ? label.textContent.toLowerCase() : '';
    option.style.display = text.includes(searchText) ? 'flex' : 'none';
  });
}

function toggleFilterSelection(filterName, value) {
  const index = selectedFilters[filterName].indexOf(value);

  if (index > -1) {
    selectedFilters[filterName].splice(index, 1);
  } else {
    selectedFilters[filterName].push(value);
  }

  updateSelectedDisplay(filterName);
}

function updateSelectedDisplay(filterName) {
  const selectedContainer = document.getElementById(`${filterName}Selected`);
  if (!selectedContainer) return;

  selectedContainer.innerHTML = '';

  selectedFilters[filterName].forEach(value => {
    const tag = document.createElement('span');
    tag.className = 'filter-selected-item';
    tag.innerHTML = `
      ${value}
      <span class="filter-selected-item-remove" onclick="removeFilterSelection('${filterName}', '${value.replace(/'/g, "\\'")}')">×</span>
    `;
    selectedContainer.appendChild(tag);
  });
}

function removeFilterSelection(filterName, value) {
  const index = selectedFilters[filterName].indexOf(value);
  if (index > -1) {
    selectedFilters[filterName].splice(index, 1);
  }

  // Uncheck the checkbox
  const checkbox = document.querySelector(`#${filterName}Options input[value="${value}"]`);
  if (checkbox) {
    checkbox.checked = false;
  }

  updateSelectedDisplay(filterName);
}

// ============ COLUMN VISIBILITY FUNCTIONS ============

function populateColumnVisibilityDropdown() {
  const optionsContainer = document.getElementById('columnVisibilityOptions');
  if (!optionsContainer) return;

  optionsContainer.innerHTML = '';

  availableColumns.forEach(column => {
    const optionDiv = document.createElement('div');
    optionDiv.className = 'filter-dropdown-option';
    optionDiv.setAttribute('data-value', column.key);

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = `colVis_${column.key}`;
    checkbox.value = column.key;
    checkbox.checked = visibleColumns[column.key];
    checkbox.onchange = () => toggleColumnVisibility(column.key);

    const label = document.createElement('label');
    label.htmlFor = checkbox.id;
    label.textContent = column.label;

    optionDiv.appendChild(checkbox);
    optionDiv.appendChild(label);
    optionsContainer.appendChild(optionDiv);
  });
}

function showColumnVisibilityDropdown() {
  const dropdown = document.getElementById('columnVisibilityDropdown');
  if (dropdown) {
    dropdown.classList.remove('hidden');
  }
}

function filterColumnVisibilityOptions() {
  const searchInput = document.getElementById('columnVisibilitySearchInput');
  const optionsContainer = document.getElementById('columnVisibilityOptions');

  if (!searchInput || !optionsContainer) return;

  const searchText = searchInput.value.toLowerCase();
  const options = optionsContainer.querySelectorAll('.filter-dropdown-option');

  options.forEach(option => {
    const label = option.querySelector('label');
    const text = label ? label.textContent.toLowerCase() : '';
    option.style.display = text.includes(searchText) ? 'flex' : 'none';
  });
}

function toggleColumnVisibility(columnKey) {
  visibleColumns[columnKey] = !visibleColumns[columnKey];
}

/**
 * Initialize the sentiment score slider with min/max values from backend
 */
async function initializeSentimentSlider(projectId) {
  const minSlider = document.getElementById('sentimentSliderMin');
  const maxSlider = document.getElementById('sentimentSliderMax');
  const minInput = document.getElementById('minSentiment');
  const maxInput = document.getElementById('maxSentiment');
  const rangeEl = document.getElementById('sentimentSliderRange');
  const labelMin = document.getElementById('sentimentLabelMin');
  const labelMid = document.getElementById('sentimentLabelMid');
  const labelMax = document.getElementById('sentimentLabelMax');

  if (!minSlider || !maxSlider || !minInput || !maxInput) return;

  let dataMin = 1.0;
  let dataMax = 5.0;

  try {
    // Fetch sentiment range from backend
    const response = await fetch(`${API_BASE}/api/projects/${projectId}/sentiment-range`);
    const result = await response.json();

    if (result.success) {
      dataMin = result.min_sentiment || 1.0;
      dataMax = result.max_sentiment || 5.0;
    }
  } catch (error) {
    console.error('Error fetching sentiment range:', error);
  }

  // Set slider min/max attributes
  minSlider.min = dataMin;
  minSlider.max = dataMax;
  maxSlider.min = dataMin;
  maxSlider.max = dataMax;

  // Restore previously selected values if they exist, otherwise use full range
  const currentMin = (selectedFilters.sentimentMin !== null && selectedFilters.sentimentMin !== undefined)
    ? selectedFilters.sentimentMin
    : dataMin;
  const currentMax = (selectedFilters.sentimentMax !== null && selectedFilters.sentimentMax !== undefined)
    ? selectedFilters.sentimentMax
    : dataMax;

  minSlider.value = currentMin;
  maxSlider.value = currentMax;

  // Update labels
  labelMin.textContent = dataMin.toFixed(2);
  labelMid.textContent = ((dataMin + dataMax) / 2).toFixed(2);
  labelMax.textContent = dataMax.toFixed(2);

  // Update input boxes with current values
  minInput.value = currentMin.toFixed(2);
  maxInput.value = currentMax.toFixed(2);

  // Update filters with current values
  selectedFilters.sentimentMin = currentMin;
  selectedFilters.sentimentMax = currentMax;

  // Function to update the visual range overlay
  const updateRange = () => {
    const min = parseFloat(minSlider.value);
    const max = parseFloat(maxSlider.value);

    // Prevent crossing
    if (min > max - 0.01) {
      minSlider.value = max - 0.01;
    }
    if (max < min + 0.01) {
      maxSlider.value = min + 0.01;
    }

    const actualMin = parseFloat(minSlider.value);
    const actualMax = parseFloat(maxSlider.value);

    // Update input boxes
    minInput.value = actualMin.toFixed(2);
    maxInput.value = actualMax.toFixed(2);

    // Update filters
    selectedFilters.sentimentMin = actualMin;
    selectedFilters.sentimentMax = actualMax;

    // Update visual range
    const percentMin = ((actualMin - dataMin) / (dataMax - dataMin)) * 100;
    const percentMax = ((actualMax - dataMin) / (dataMax - dataMin)) * 100;

    rangeEl.style.left = percentMin + '%';
    rangeEl.style.width = (percentMax - percentMin) + '%';
  };

  // Attach event listeners
  minSlider.addEventListener('input', updateRange);
  maxSlider.addEventListener('input', updateRange);

  // Initial range update
  updateRange();

  // Store reference for clear function
  sentimentSlider = {
    reset: () => {
      minSlider.value = dataMin;
      maxSlider.value = dataMax;
      updateRange();
    },
    getRange: () => ({ min: dataMin, max: dataMax })
  };
}

/**
 * Initialize duration slider (similar to sentiment slider)
 */
async function initializeDurationSlider(projectId) {
  const minSlider = document.getElementById('durationSliderMin');
  const maxSlider = document.getElementById('durationSliderMax');
  const minInput = document.getElementById('minDuration');
  const maxInput = document.getElementById('maxDuration');
  const rangeEl = document.getElementById('durationSliderRange');
  const labelMin = document.getElementById('durationLabelMin');
  const labelMid = document.getElementById('durationLabelMid');
  const labelMax = document.getElementById('durationLabelMax');

  if (!minSlider || !maxSlider || !minInput || !maxInput) return;

  let dataMin = 0;
  let dataMax = 1000;

  try {
    // Fetch duration range from backend
    const response = await fetch(`${API_BASE}/api/projects/${projectId}/duration-range`);
    const result = await response.json();

    if (result.success) {
      dataMin = result.min_duration || 0;
      dataMax = result.max_duration || 1000;
    }
  } catch (error) {
    console.error('Error fetching duration range:', error);
  }

  // Set slider min/max attributes
  minSlider.min = dataMin;
  minSlider.max = dataMax;
  maxSlider.min = dataMin;
  maxSlider.max = dataMax;

  // Restore previously selected values if they exist, otherwise use full range
  const currentMin = (selectedFilters.durationMin !== null && selectedFilters.durationMin !== undefined)
    ? selectedFilters.durationMin
    : dataMin;
  const currentMax = (selectedFilters.durationMax !== null && selectedFilters.durationMax !== undefined)
    ? selectedFilters.durationMax
    : dataMax;

  minSlider.value = currentMin;
  maxSlider.value = currentMax;

  // Update labels
  labelMin.textContent = Math.round(dataMin);
  labelMid.textContent = Math.round((dataMin + dataMax) / 2);
  labelMax.textContent = Math.round(dataMax);

  // Update input boxes with current values
  minInput.value = Math.round(currentMin);
  maxInput.value = Math.round(currentMax);

  // Update filters with current values
  selectedFilters.durationMin = currentMin;
  selectedFilters.durationMax = currentMax;

  // Function to update the visual range overlay
  const updateRange = () => {
    const min = parseFloat(minSlider.value);
    const max = parseFloat(maxSlider.value);

    // Prevent crossing
    if (min > max - 1) {
      minSlider.value = max - 1;
    }
    if (max < min + 1) {
      maxSlider.value = min + 1;
    }

    const actualMin = parseFloat(minSlider.value);
    const actualMax = parseFloat(maxSlider.value);

    // Update input boxes
    minInput.value = Math.round(actualMin);
    maxInput.value = Math.round(actualMax);

    // Update filters
    selectedFilters.durationMin = actualMin;
    selectedFilters.durationMax = actualMax;

    // Update visual range
    const percentMin = ((actualMin - dataMin) / (dataMax - dataMin)) * 100;
    const percentMax = ((actualMax - dataMin) / (dataMax - dataMin)) * 100;

    rangeEl.style.left = percentMin + '%';
    rangeEl.style.width = (percentMax - percentMin) + '%';
  };

  // Attach event listeners
  minSlider.addEventListener('input', updateRange);
  maxSlider.addEventListener('input', updateRange);

  // Initial range update
  updateRange();

  // Store reference for clear function
  durationSlider = {
    reset: () => {
      minSlider.value = dataMin;
      maxSlider.value = dataMax;
      updateRange();
    },
    getRange: () => ({ min: dataMin, max: dataMax })
  };
}

/**
 * Aggregates data based on visible columns only.
 * Rows that differ only in hidden columns will be merged with Volume summed.
 * Hidden column values are stored as arrays to preserve all unique values.
 */
function aggregateDataByVisibleColumns(data, visibleCols) {
  if (!data || data.length === 0) return data;

  // Get list of visible and hidden column keys
  const allKeys = ['Category', 'Topic', 'Intent', 'Agent_Task'];
  const visibleKeys = allKeys.filter(key => visibleCols[key] !== false);
  const hiddenKeys = allKeys.filter(key => visibleCols[key] === false);

  // Group rows by visible columns
  const grouped = {};

  data.forEach(row => {
    // Create a unique key based on visible columns only
    const keyParts = visibleKeys.map(key => row[key] || 'N/A');
    const groupKey = keyParts.join('|');

    if (!grouped[groupKey]) {
      // Initialize new group with first row's data
      grouped[groupKey] = { ...row, Volume: 0 };

      // For visible columns, use the value
      visibleKeys.forEach(key => {
        grouped[groupKey][key] = row[key];
      });

      // For hidden columns, initialize arrays to track all unique values
      hiddenKeys.forEach(key => {
        grouped[groupKey][`_hidden_${key}`] = [];
      });
    }

    // Sum the Volume
    grouped[groupKey].Volume += row.Volume;

    // Collect all unique values for hidden columns
    hiddenKeys.forEach(key => {
      const value = row[key];
      const hiddenArray = grouped[groupKey][`_hidden_${key}`];
      if (!hiddenArray.includes(value)) {
        hiddenArray.push(value);
      }
      // Also keep one value in the regular field for display purposes
      if (!grouped[groupKey][key]) {
        grouped[groupKey][key] = value;
      }
    });
  });

  return Object.values(grouped);
}

async function applyFilters() {
  // Get IsAutomatable toggle value
  const isAutomatableToggle = document.getElementById('isAutomatableToggle');
  selectedFilters.isAutomatable = isAutomatableToggle ? isAutomatableToggle.checked : false;

  console.log('Applying filters:', selectedFilters);
  console.log('Visible columns:', visibleColumns);

  // Get current project
  const projectIdInput = document.getElementById('chatProjectSearch');
  const projectId = projectIdInput ? projectIdInput.getAttribute('data-selected-id') : null;
  const projectName = projectIdInput ? projectIdInput.value : '';

  if (!projectId) {
    alert('Please select a project first');
    return;
  }

  // Reload the table with filters
  await fetchAndDisplayProjectSummary(projectId, projectName, selectedFilters, visibleColumns);

  closeFilterPanel();
}

async function clearAllFilters() {
  // Reset all filters
  selectedFilters = {
    category: [],
    topic: [],
    intent: [],
    agentTask: [],
    isAutomatable: false,
    sentimentMin: null,
    sentimentMax: null,
    durationMin: null,
    durationMax: null
  };

  // Uncheck all checkboxes
  document.querySelectorAll('.filter-dropdown-option input[type="checkbox"]').forEach(cb => {
    cb.checked = false;
  });

  // Clear all selected displays
  ['category', 'topic', 'intent', 'agentTask'].forEach(filterName => {
    updateSelectedDisplay(filterName);
  });

  // Uncheck IsAutomatable toggle
  const isAutomatableToggle = document.getElementById('isAutomatableToggle');
  if (isAutomatableToggle) {
    isAutomatableToggle.checked = false;
  }

  // Reset sentiment slider to full range
  if (sentimentSlider && sentimentSlider.reset) {
    sentimentSlider.reset();
  }

  // Reset duration slider to full range
  if (durationSlider && durationSlider.reset) {
    durationSlider.reset();
  }

  // Get current project
  const projectIdInput = document.getElementById('chatProjectSearch');
  const projectId = projectIdInput ? projectIdInput.getAttribute('data-selected-id') : null;
  const projectName = projectIdInput ? projectIdInput.value : '';

  if (!projectId) {
    alert('Please select a project first');
    return;
  }

  // Reload the table without filters
  await fetchAndDisplayProjectSummary(projectId, projectName, null);

  closeFilterPanel();
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const createPanel = document.getElementById('createProjectPanel');
    const filterPanel = document.getElementById('filterPanel');

    if (createPanel && createPanel.classList.contains('is-open')) {
      closeCreateProject();
    }
    if (filterPanel && filterPanel.classList.contains('is-open')) {
      closeFilterPanel();
    }

    // Close any open filter dropdowns
    document.querySelectorAll('.filter-dropdown').forEach(dropdown => {
      dropdown.classList.add('hidden');
    });
  }
});

// Close dropdowns when clicking outside
document.addEventListener('click', (e) => {
  const isSearchInput = e.target.closest('.filter-multiselect-container input');
  const isDropdownOption = e.target.closest('.filter-dropdown-option');

  if (!isSearchInput && !isDropdownOption) {
    document.querySelectorAll('.filter-dropdown').forEach(dropdown => {
      dropdown.classList.add('hidden');
    });
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
      // Auto-close panel after failure
      closeCreateProject();
    }

  } catch (error) {
    console.error('Network error:', error);
    addFailedResultToTable({
      projectName: projectName,
      fileName: uploadedCSVFile.name,
      errors: ['Failed to connect to server. Make sure Flask backend is running.']
    });
    // Auto-close panel after error
    closeCreateProject();
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
            // Projects are already ordered by created_at DESC from backend (newest first)
            // No need to sort alphabetically - keep chronological order
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

                // Auto-select the latest (first) project and load its data
                const latestProject = successfulProjects[0];
                selectChatProject(latestProject.id, latestProject.name);
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
 * @param {number} projectId - The project ID
 * @param {string} projectName - The project name
 * @param {object} filters - Optional filter object with category, topic, intent, agentTask, isAutomatable
 * @param {object} visibleCols - Optional visible columns object {Category: true, Topic: true, ...}
 */
async function fetchAndDisplayProjectSummary(projectId, projectName, filters = null, visibleCols = null) {
    const landingMain = document.querySelector('.landing-main');

    // Remove any existing temporary content (no loading message)
    const tempContent = document.getElementById('temporaryViewContent');
    if (tempContent) {
        tempContent.remove();
    }

    try {
        // Build query parameters from filters
        let url = `${API_BASE}/api/projects/${projectId}/summary`;
        const params = new URLSearchParams();

        if (filters) {
            if (filters.category && filters.category.length > 0) {
                params.append('categories', filters.category.join(','));
            }
            if (filters.topic && filters.topic.length > 0) {
                params.append('topics', filters.topic.join(','));
            }
            if (filters.intent && filters.intent.length > 0) {
                params.append('intents', filters.intent.join(','));
            }
            if (filters.agentTask && filters.agentTask.length > 0) {
                params.append('agent_tasks', filters.agentTask.join(','));
            }
            if (filters.isAutomatable) {
                params.append('is_automatable', '1');
            }
            if (filters.sentimentMin !== null && filters.sentimentMin !== undefined) {
                params.append('sentiment_min', filters.sentimentMin);
            }
            if (filters.sentimentMax !== null && filters.sentimentMax !== undefined) {
                params.append('sentiment_max', filters.sentimentMax);
            }
            if (filters.durationMin !== null && filters.durationMin !== undefined) {
                params.append('duration_min', filters.durationMin);
            }
            if (filters.durationMax !== null && filters.durationMax !== undefined) {
                params.append('duration_max', filters.durationMax);
            }
        }

        // Add visible columns to GROUP BY only those columns
        // This prevents double-counting when columns are hidden
        if (visibleCols) {
            const groupByColumns = [];
            if (visibleCols.Category !== false) groupByColumns.push('category');
            if (visibleCols.Topic !== false) groupByColumns.push('topic');
            if (visibleCols.Intent !== false) groupByColumns.push('intent');
            if (visibleCols.Agent_Task !== false) groupByColumns.push('agent_task');
            if (groupByColumns.length > 0) {
                params.append('group_by', groupByColumns.join(','));
            }
        }

        if (params.toString()) {
            url += '?' + params.toString();
        }

        console.log('Fetching summary with URL:', url);
        const response = await fetch(url);

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
 * Note: Data is already properly aggregated by backend based on visible columns,
 * so we don't need client-side aggregation anymore.
 */
function createChatSummaryTable(data, projectName, message = null) {
    const landingMain = document.querySelector('.landing-main');

    // Store data directly - backend already aggregated based on visible columns
    currentChatData = data;
    currentSortColumn = 'Volume';
    currentSortDirection = 'desc';

    // Define all possible columns
    const allColumnDefinitions = [
        { key: 'Category', label: 'Category', sortable: true },
        { key: 'Topic', label: 'Topic', sortable: true },
        { key: 'Intent', label: 'Intent', sortable: true },
        { key: 'Agent_Task', label: 'Agent Task', sortable: true },
        { key: 'Volume', label: 'Volume', sortable: true, type: 'number' },
        { key: 'AI_Chat', label: 'AI Chat', sortable: false, isIcon: true }
    ];

    // Filter columns based on visibility settings (always show Volume and AI_Chat)
    const columnDefinitions = allColumnDefinitions.filter(col => {
        if (col.key === 'Volume' || col.key === 'AI_Chat') {
            return true; // Always show Volume and AI Chat
        }
        return visibleColumns[col.key] !== false;
    });

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
                    // Pass all 4 fields to uniquely identify the row
                    const escIntent = (row.Intent || '').replace(/'/g, "\\'");
                    const escTopic = (row.Topic || '').replace(/'/g, "\\'");
                    const escCategory = (row.Category || '').replace(/'/g, "\\'");
                    const escAgentTask = (row.Agent_Task || '').replace(/'/g, "\\'");
                    return `<td style="${flexStyle} text-align: center; min-width: 0;"><img src="assets/img/bot-builder.svg" alt="Chat" style="width: 24px; height: 24px; cursor: pointer;" onclick="openAIChat('${escIntent}', '${escTopic}', '${escCategory}', '${escAgentTask}')"/></td>`;
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

    // 1. Sort data by Volume DESC
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
                // Pass all 4 fields to uniquely identify the row
                const escIntent = (row.Intent || '').replace(/'/g, "\\'");
                const escTopic = (row.Topic || '').replace(/'/g, "\\'");
                const escCategory = (row.Category || '').replace(/'/g, "\\'");
                const escAgentTask = (row.Agent_Task || '').replace(/'/g, "\\'");
                return `<td style="${flexStyle} text-align: center; min-width: 0;"><img src="assets/img/bot-builder.svg" alt="Chat" style="width: 24px; height: 24px; cursor: pointer;" onclick="openAIChat('${escIntent}', '${escTopic}', '${escCategory}', '${escAgentTask}')"/></td>`;
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

// Global state for current chat session
let currentChatContext = {
    projectId: null,
    filters: {},
    conversationHistory: []
};

async function openAIChat(intent, topic, category, agentTask) {
    console.log('Opening AI Chat for:', { intent, topic, category, agentTask });

    // Get the selected project ID from the dropdown
    const projectIdInput = document.getElementById('chatProjectSearch');
    const projectId = projectIdInput ? projectIdInput.getAttribute('data-selected-id') : null;

    if (!projectId) {
        alert('Please select a project first');
        return;
    }

    // Get the exact row data by matching ALL 4 fields to uniquely identify the row
    const rows = currentChatData.filter(row =>
        row.Intent === intent &&
        row.Topic === topic &&
        row.Category === category &&
        row.Agent_Task === agentTask
    );

    if (rows.length === 0) {
        alert('Could not find matching data');
        return;
    }

    const rowData = rows[0];

    // Build filters combining the row's specific values for VISIBLE columns
    // For HIDDEN columns: use the filter panel selections (if any)
    const chatFilters = {};

    // Category filter
    if (visibleColumns.Category !== false) {
        chatFilters.category = rowData.Category;
    } else if (selectedFilters && selectedFilters.category && selectedFilters.category.length > 0) {
        chatFilters.categories = selectedFilters.category.join(',');
    }

    // Topic filter
    if (visibleColumns.Topic !== false) {
        chatFilters.topic = rowData.Topic;
    } else if (selectedFilters && selectedFilters.topic && selectedFilters.topic.length > 0) {
        chatFilters.topics = selectedFilters.topic.join(',');
    }

    // Intent filter
    if (visibleColumns.Intent !== false) {
        chatFilters.intent = rowData.Intent;
    } else if (selectedFilters && selectedFilters.intent && selectedFilters.intent.length > 0) {
        chatFilters.intents = selectedFilters.intent.join(',');
    }

    // Agent Task filter
    if (visibleColumns.Agent_Task !== false) {
        chatFilters.agent_task = rowData.Agent_Task;
    } else if (selectedFilters && selectedFilters.agentTask && selectedFilters.agentTask.length > 0) {
        chatFilters.agent_tasks = selectedFilters.agentTask.join(',');
    }

    // Include IsAutomatable filter if it was applied to the table
    if (selectedFilters && selectedFilters.isAutomatable) {
        chatFilters.is_automatable = '1';
    }

    // Include sentiment filters if they were applied to the table
    if (selectedFilters && selectedFilters.sentimentMin !== null && selectedFilters.sentimentMin !== undefined) {
        chatFilters.sentiment_min = selectedFilters.sentimentMin;
    }
    if (selectedFilters && selectedFilters.sentimentMax !== null && selectedFilters.sentimentMax !== undefined) {
        chatFilters.sentiment_max = selectedFilters.sentimentMax;
    }

    // Include duration filters if they were applied to the table
    if (selectedFilters && selectedFilters.durationMin !== null && selectedFilters.durationMin !== undefined) {
        chatFilters.duration_min = selectedFilters.durationMin;
    }
    if (selectedFilters && selectedFilters.durationMax !== null && selectedFilters.durationMax !== undefined) {
        chatFilters.duration_max = selectedFilters.durationMax;
    }

    console.log('🔍 Chat Filters being sent:', chatFilters);

    // Store chat context
    currentChatContext = {
        projectId: projectId,
        filters: chatFilters,
        conversationHistory: []
    };

    // Update subtitle with context info - only show visible columns
    const subtitle = document.getElementById('aiChatSubtitle');
    if (subtitle) {
        const subtitleParts = [];
        if (visibleColumns.Category !== false) {
            subtitleParts.push(rowData.Category);
        }
        if (visibleColumns.Topic !== false) {
            subtitleParts.push(rowData.Topic);
        }
        if (visibleColumns.Intent !== false) {
            subtitleParts.push(rowData.Intent);
        }
        if (visibleColumns.Agent_Task !== false) {
            subtitleParts.push(rowData.Agent_Task);
        }
        subtitle.textContent = `${subtitleParts.join(' > ')} (${rowData.Volume} transcripts)`;
    }

    // Show modal with loading indicator
    const modal = document.getElementById('aiChatModal');
    const messagesContainer = document.getElementById('aiChatMessages');

    if (modal) {
        modal.classList.remove('hidden');
        modal.setAttribute('aria-hidden', 'false');
    }

    // Show loading indicator while preparing chat context
    if (messagesContainer) {
        messagesContainer.innerHTML = `
            <div class="ai-chat-message ai-chat-message-system">
                <div class="ai-chat-message-content">
                    <p><strong>🔄 Preparing chat session...</strong></p>
                    <p>Loading ${rowData.Volume} transcripts, please wait...</p>
                    <div class="ai-chat-loading-spinner"></div>
                </div>
            </div>
        `;
    }

    try {
        // Pre-generate CSV file (this is the slow part - do it once upfront)
        console.log('Preparing chat context (generating CSV)...');
        const prepareResponse = await fetch(`${API_BASE}/api/projects/${projectId}/chat/prepare`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filters: currentChatContext.filters
            })
        });

        const prepareResult = await prepareResponse.json();

        if (!prepareResult.success) {
            throw new Error(prepareResult.error || 'Failed to prepare chat context');
        }

        console.log('Chat context prepared successfully!');

        // Now show the ready message
        if (messagesContainer) {
            // Build context info HTML - only show visible columns
            let contextInfo = '';
            if (visibleColumns.Category !== false) {
                contextInfo += `Category: ${rowData.Category}<br>`;
            }
            if (visibleColumns.Topic !== false) {
                contextInfo += `Topic: ${rowData.Topic}<br>`;
            }
            if (visibleColumns.Intent !== false) {
                contextInfo += `Intent: ${rowData.Intent}<br>`;
            }
            if (visibleColumns.Agent_Task !== false) {
                contextInfo += `Agent Task: ${rowData.Agent_Task}<br>`;
            }
            // Remove trailing <br>
            contextInfo = contextInfo.replace(/<br>$/, '');

            messagesContainer.innerHTML = `
                <div class="ai-chat-message ai-chat-message-system">
                    <div class="ai-chat-message-content">
                        <p><strong>✅ Chat session ready!</strong></p>
                        <p>Ask questions about the ${prepareResult.transcript_count} transcripts in this group.</p>
                        <p class="ai-chat-context-info">
                            ${contextInfo}
                        </p>
                        <button class="ai-chat-verify-btn" onclick="verifyTranscriptFiles()">
                             Verify File Access
                        </button>
                    </div>
                </div>
            `;
        }

        // Focus on input
        setTimeout(() => {
            const input = document.getElementById('aiChatInput');
            if (input) input.focus();
        }, 100);

    } catch (error) {
        console.error('Error preparing chat:', error);
        if (messagesContainer) {
            messagesContainer.innerHTML = `
                <div class="ai-chat-message ai-chat-message-error">
                    <div class="ai-chat-message-content">
                        <p><strong>❌ Error preparing chat</strong></p>
                        <p>${error.message}</p>
                        <p>Please try again or contact support.</p>
                    </div>
                </div>
            `;
        }
    }
}

function closeAIChat() {
    const modal = document.getElementById('aiChatModal');
    if (modal) {
        modal.classList.add('hidden');
        modal.setAttribute('aria-hidden', 'true');
    }

    // Clear input
    const input = document.getElementById('aiChatInput');
    if (input) input.value = '';
}

async function verifyTranscriptFiles() {
    if (!currentChatContext.projectId) {
        alert('No project selected');
        return;
    }

    // Show loading message
    addChatMessage('system', 'Verifying transcript file accessibility...');

    try {
        const response = await fetch(`${API_BASE}/api/projects/${currentChatContext.projectId}/chat/verify`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filters: currentChatContext.filters,
                sample_size: 10  // Check first 10 files
            })
        });

        const result = await response.json();

        if (result.success) {
            let message = `**File Access Verification Results:**\n\n`;

            // System info
            if (result.system_info) {
                message += `**Server Environment:**\n`;
                message += `- Platform: ${result.system_info.platform} (${result.system_info.platform_details})\n`;
                message += `- Python: ${result.system_info.python_version}\n`;
                message += `- Path mappings configured: ${result.system_info.path_mappings_configured ? 'Yes' : '❌ No'}\n\n`;
            }

            message += `**File Summary:**\n`;
            message += `Total files: ${result.total_files}\n`;
            message += `Sample checked: ${result.sample_checked}\n`;
            message += `✅ Accessible: ${result.accessible}\n`;
            message += `❌ Inaccessible: ${result.inaccessible}\n\n`;

            if (result.sample_results && result.sample_results.length > 0) {
                message += `**Sample Details:**\n`;
                result.sample_results.forEach((sample, idx) => {
                    message += `\n${idx + 1}. ${sample.interaction_id}:\n`;
                    if (sample.accessible) {
                        message += `   ✅ Accessible (${sample.turn_count} turns, ${(sample.file_size / 1024).toFixed(1)} KB)\n`;
                    } else {
                        message += `   ❌ Not accessible\n`;
                        message += `   Error: ${sample.error}\n`;
                        if (sample.conversion_notes) {
                            message += `   Notes: ${sample.conversion_notes}\n`;
                        }
                        if (sample.suggestion) {
                            message += `   💡 ${sample.suggestion}\n`;
                        }
                        message += `   Path: ${sample.file_path}\n`;
                    }
                });
            }

            if (result.inaccessible > 0) {
                message += `\n\n⚠️ **Problem Detected:**\n`;

                if (result.system_info && result.system_info.platform === 'Linux' && !result.system_info.path_mappings_configured) {
                    message += `Your Flask server is running on Linux, but Windows UNC paths (\\\\\\\\server\\\\share) won't work.\n\n`;
                    message += `**Solutions:**\n`;
                    message += `1. **Mount the network share** on your Linux server:\n`;
                    message += `   \`sudo mount -t cifs //VAOD177APP05/Media /mnt/media -o username=your_user\`\n\n`;
                    message += `2. **Configure PATH_MAPPINGS** in flask_backend.py:\n`;
                    message += `   \`PATH_MAPPINGS = {'\\\\\\\\\\\\\\\\VAOD177APP05\\\\\\\\Media': '/mnt/media'}\`\n\n`;
                    message += `3. **Run Flask on Windows** where UNC paths work natively\n`;
                } else if (result.system_info && result.system_info.platform === 'Windows') {
                    message += `Server is on Windows but files still not accessible.\n`;
                    message += `- Check if you have network permissions\n`;
                    message += `- Try accessing \\\\\\\\VAOD177APP05\\\\Media from the server\n`;
                    message += `- Ensure Flask runs with correct user credentials\n`;
                }
            } else {
                message += `\n✅ **All sampled files are accessible!** You can now use the AI chat.`;
            }

            addChatMessage('system', message);
        } else {
            addChatMessage('error', `Verification failed: ${result.error}`);
        }

    } catch (error) {
        console.error('Verification error:', error);
        addChatMessage('error', 'Failed to verify files. Check that backend is running.');
    }
}

async function sendChatMessage() {
    const input = document.getElementById('aiChatInput');
    const sendBtn = document.getElementById('aiChatSendBtn');
    const messagesContainer = document.getElementById('aiChatMessages');

    if (!input || !messagesContainer) return;

    const question = input.value.trim();
    if (!question) return;

    // Disable input while processing
    input.disabled = true;
    sendBtn.disabled = true;
    const originalBtnContent = sendBtn.innerHTML;
    sendBtn.innerHTML = '<span style="font-size: 12px;">...</span>';

    // Add user message to UI
    addChatMessage('user', question);

    // Clear input
    input.value = '';

    // Store in conversation history
    currentChatContext.conversationHistory.push({
        role: 'user',
        content: question
    });

    // Show "AI Thinking" indicator
    const thinkingDiv = document.createElement('div');
    thinkingDiv.className = 'ai-chat-message ai-chat-message-thinking';
    thinkingDiv.id = 'ai-thinking-indicator';
    thinkingDiv.innerHTML = `
        <div class="ai-chat-message-content">
            <p><strong>🤔 AI is thinking...</strong></p>
            <div class="ai-chat-loading-spinner"></div>
        </div>
    `;
    messagesContainer.appendChild(thinkingDiv);

    // Scroll to show thinking indicator
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    try {
        // Call backend API
        const response = await fetch(`${API_BASE}/api/projects/${currentChatContext.projectId}/chat/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filters: currentChatContext.filters,
                question: question
            })
        });

        const result = await response.json();

        // Remove thinking indicator
        const thinkingIndicator = document.getElementById('ai-thinking-indicator');
        if (thinkingIndicator) {
            thinkingIndicator.remove();
        }

        if (result.success) {
            // Add AI response to UI
            addChatMessage('assistant', result.answer, {
                transcriptCount: result.transcript_count,
                tokensUsed: result.tokens_used
            });

            // Store in conversation history
            currentChatContext.conversationHistory.push({
                role: 'assistant',
                content: result.answer
            });
        } else {
            // Show error message
            addChatMessage('error', `Error: ${result.error}`);
        }

    } catch (error) {
        console.error('Chat error:', error);

        // Remove thinking indicator on error too
        const thinkingIndicator = document.getElementById('ai-thinking-indicator');
        if (thinkingIndicator) {
            thinkingIndicator.remove();
        }

        addChatMessage('error', 'Failed to connect to AI service. Please check that the backend is running and AWS credentials are configured.');
    } finally {
        // Re-enable input
        input.disabled = false;
        sendBtn.disabled = false;
        sendBtn.innerHTML = originalBtnContent;
        input.focus();
    }
}

function addChatMessage(role, content, metadata = null) {
    const messagesContainer = document.getElementById('aiChatMessages');
    if (!messagesContainer) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = `ai-chat-message ai-chat-message-${role}`;

    let messageHTML = `<div class="ai-chat-message-content">`;

    if (role === 'user') {
        messageHTML += `
            <div class="ai-chat-message-label">You</div>
            <p>${escapeHtml(content)}</p>
        `;
    } else if (role === 'assistant') {
        messageHTML += `
            <div class="ai-chat-message-label">AI Assistant</div>
            <div class="ai-chat-message-text">${formatAIResponse(content)}</div>
        `;

        if (metadata) {
            messageHTML += `
                <div class="ai-chat-metadata">
                    <small>Analyzed ${metadata.transcriptCount} transcripts |
                    Tokens: ${metadata.tokensUsed.input} in, ${metadata.tokensUsed.output} out</small>
                </div>
            `;
        }
    } else if (role === 'system') {
        messageHTML += `
            <div class="ai-chat-message-label">System</div>
            <div class="ai-chat-message-text">${formatAIResponse(content)}</div>
        `;
    } else if (role === 'error') {
        messageHTML += `
            <div class="ai-chat-message-label">Error</div>
            <p style="color: #d32f2f;">${escapeHtml(content)}</p>
        `;
    }

    messageHTML += `</div>`;
    messageDiv.innerHTML = messageHTML;

    messagesContainer.appendChild(messageDiv);

    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function formatAIResponse(text) {
    // Simple markdown-like formatting
    // Convert newlines to <br>
    let formatted = escapeHtml(text);

    // Bold text: **text** -> <strong>text</strong>
    formatted = formatted.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Convert newlines to paragraphs
    formatted = formatted.split('\n\n').map(para => `<p>${para.replace(/\n/g, '<br>')}</p>`).join('');

    return formatted;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Handle Enter key in chat input (Shift+Enter for new line, Enter to send)
document.addEventListener('DOMContentLoaded', () => {
    const chatInput = document.getElementById('aiChatInput');
    if (chatInput) {
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendChatMessage();
            }
        });

        // Auto-resize textarea
        chatInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 120) + 'px';
        });
    }
});


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