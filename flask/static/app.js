let ruleType = "dnat";
let dnatButton = document.getElementById("dnat-btn");
let snatButton = document.getElementById("snat-btn");
let bottomContainer = document.getElementById("bottom-container");
let dnatTable = document.getElementById("dnat-table");
let snatTable = document.getElementById("snat-table");
let tempDeleteButton = document.getElementById("temp-delete-btn");
let tempDropDown = document.getElementById("temp-dropdown");
let tempDropDownSNATProtocol = document.getElementById("temp-dropdown-snat-protocol");
let tempDropDownSNAT = document.getElementById("temp-dropdown-2");
let dashboardPollTimer = null;
let snatInterfaceOptions = [];

console.log("V1.6.1 Loaded");

function updateDropDowns() {
  //console.log("Updating Dropdowns");
  var dropdowns = document.getElementsByClassName('select');
  for (var obj of dropdowns) {
    if (obj.className === 'select') {
      var options = obj.children;
      //console.log("Object Dropdown" + obj);
      for (let child of options) {
        if (obj.getAttribute('value') === child.getAttribute('value')) {
          child.setAttribute("selected", "");
        }
      }
    }
  }
}

//Drop-down menu modifier
$(document).ready(function () {
  console.log(" - Document Ready - ");

  //Default the correct drop-down selection for protocol
  updateDropDowns();
  loadVnicState();
  loadBackupState();
  startDashboardStream();

  //Update select element value when selection changes
  $(document).on('change', '.dropper', function () {
    //console.log("Dropdown changing.");
    //alert($(this).val());
    $(this).attr("value", $(this).val());
    //console.log($(this).val());
  });

})

function changeMenu(menu) {
  if (menu === "dnat") {
    //console.log("Clicked DNAT")
    dnatButton.className = "btn btn-primary btn-lg";
    snatButton.className = "btn btn-outline-primary btn-lg";

    try {
      dnatTable.className = "table";
      snatTable.className = "table d-none";
    } catch (error) {
      console.log(error);
    }

    bottomContainer.className = "container mt-3";
    ruleType = "dnat";
  } else if (menu === "snat") {
    //console.log("Clicked SNAT")
    snatButton.className = "btn btn-primary btn-lg";
    dnatButton.className = "btn btn-outline-primary btn-lg";

    try {
      dnatTable.className = "table d-none";
      snatTable.className = "table";
    } catch (error) {
      console.log(error);
    }

    bottomContainer.className = "container mt-3";
    ruleType = "snat";
  } else {
    console.log("Something went wrong!");
  }
}


function add_row_dnat() {
  //console.log("add dnat row");
  var table = dnatTable.getElementsByTagName('tbody')[0];

  var cloned_delete_dnat = tempDeleteButton.cloneNode(true);
  cloned_delete_dnat.id = "";
  cloned_delete_dnat.className = "";

  var cloned_dropdown_dnat = tempDropDown.cloneNode(true);
  cloned_dropdown_dnat.id = "dropdown-dnat";
  cloned_dropdown_dnat.className = "select dropper";

  try {
    var loc = table.rows.length;
    //console.log(loc);
  } catch (error) {
    var loc = 0;
  }
  var table_id = loc - 1;
  var row = table.insertRow();
  row.id = "dnat_row_" + table_id;
  var cell0 = row.insertCell(0);
  var cell1 = row.insertCell(1);
  var cell2 = row.insertCell(2);
  var cell3 = row.insertCell(3);
  var cell4 = row.insertCell(4);
  var cell5 = row.insertCell(5);
  cell0.innerHTML = "<div>" + table_id + "</div>";
  cell1.appendChild(cloned_dropdown_dnat);
  cell2.innerHTML = "<div contenteditable>-</div>";
  cell3.innerHTML = "<div contenteditable>-</div>";
  cell4.innerHTML = "<div contenteditable>-</div>";
  cell5.appendChild(cloned_delete_dnat);
  organizeRules();
}

function add_row_snat() {
  //console.log("add snat row");
  var table = snatTable.getElementsByTagName('tbody')[0];
  var cloned_delete_snat = tempDeleteButton.cloneNode(true);
  cloned_delete_snat.id = "";
  cloned_delete_snat.className = "";

  var cloned_dropdown_snat = tempDropDownSNATProtocol.cloneNode(true);
  cloned_dropdown_snat.id = "dropdown-snat";
  cloned_dropdown_snat.className = "select dropper";

  var cloned_dropdown_snat2 = tempDropDownSNAT.cloneNode(true);
  cloned_dropdown_snat2.id = "dropdown-snat2";
  cloned_dropdown_snat2.className = "select dropper";

  try {
    var loc = table.rows.length;
  } catch (error) {
    var loc = 0;
  }
  var table_id = loc - 1;
  var row = table.insertRow();
  row.id = "snat_row_" + table_id;
  var cell0 = row.insertCell(0);
  var cell1 = row.insertCell(1);
  var cell2 = row.insertCell(2);
  var cell3 = row.insertCell(3);
  var cell4 = row.insertCell(4);
  var cell5 = row.insertCell(5);
  cell0.innerHTML = "<div>" + table_id + "</div>";
  cell1.appendChild(cloned_dropdown_snat);
  cell2.appendChild(cloned_dropdown_snat2);
  cell3.innerHTML = "<div contenteditable>Null</div>";
  cell4.appendChild(snatInterfaceControl(""));
  cell5.appendChild(cloned_delete_snat);
  organizeRules();
}

function addRule() {
  if (ruleType === "dnat") {
    //console.log("Calling add_row_dnat");
    add_row_dnat();
  }
  else if (ruleType === "snat") {
    //console.log("Calling add_row_snat");
    add_row_snat();
  }
  else { console.log("Something bad happened.") };
}

function organizeRules() {
  var selected_Table;
  if (ruleType === "dnat") {
    selected_Table = dnatTable.getElementsByTagName('tbody')[0];
  }
  else if (ruleType === "snat") {
    selected_Table = snatTable.getElementsByTagName('tbody')[0];
  }
  else {
    console.log("Couldn't Identify Table for Organizing.");
  }

  try {
    for (let row = 0; row < selected_Table.rows.length; row++) {
      var tableRow = selected_Table.rows[row];
      tableRow.id = ruleType + "_row_" + row;
      tableRow.cells[0].innerHTML = "<div>" + row + "</div>";
    }
  }
  catch (error) {
    console.log(error);
  }

}

function deleteRule(rule) {
  rule.parentElement.closest('tr').remove();
  organizeRules();
}

function tableToJson() {
  var data_dnat = [];
  var table_dnat = dnatTable.getElementsByTagName('tbody')[0];
  var data_snat = [];
  var table_snat = snatTable.getElementsByTagName('tbody')[0];
  var dict = {};
  var setData;

  for (var i = 0; i < table_dnat.rows.length; i++) {
    var tableRow = table_dnat.rows[i];
    var rowData = [];
    for (var j = 0; j < tableRow.cells.length; j++) {
      if (j === 1) {
        try {
          setData = tableRow.cells[j].querySelector(".select").value;
          rowData.push(setData);
          continue;
        } catch (error) {
          console.error(error);
        }
      }
      setData = tableRow.cells[j].textContent.trim();
      rowData.push(setData);
    }
    data_dnat.push(rowData);
  }
  for (let d = 0; d < data_dnat.length; d++) {
    let predict = {};
    predict["chain"] = "PREROUTING";
    predict["protocol"] = data_dnat[d][1];
    predict["destination_port"] = data_dnat[d][2];
    predict["target"] = "DNAT";
    predict["forward_ip"] = data_dnat[d][3];
    predict["forward_port"] = data_dnat[d][4];
    dict[data_dnat[d][0]] = predict;
  }
  for (var e = 0; e < table_snat.rows.length; e++) {
    var tableRow = table_snat.rows[e];
    var rowData = [];
    for (var f = 0; f < tableRow.cells.length; f++) {
      if (f === 1 || f === 2 || f === 4) {
        try {
          setData = tableRow.cells[f].querySelector(".select").value;
          rowData.push(setData);
          continue;
        } catch (error) {
          console.error(error);
        }
      }
      //console.log("Untrimmed - " + tableRow.cells[f] + " TextContent - " + tableRow.cells[f].textContent);
      //console.log("Element Name: " + tableRow.cells[f].querySelector(".select").nodeName);
      setData = tableRow.cells[f].textContent.trim();
      //console.log("Set Data: " + setData);
      rowData.push(setData);
    }
    data_snat.push(rowData);
  }

  var total_length = data_dnat.length + data_snat.length;
  var d = 0;
  for (let dn = data_dnat.length; dn < total_length; dn++) {
    let predict = {};
    predict["chain"] = "POSTROUTING";
    predict["protocol"] = data_snat[d][1];
    predict["target"] = data_snat[d][2];
    predict["source_ip"] = data_snat[d][3];
    predict["output_interface"] = data_snat[d][4];
    if (table_snat.rows[d] && table_snat.rows[d].dataset.probability) {
      predict["probability"] = table_snat.rows[d].dataset.probability;
    }
    dict[dn] = predict;
    d++;
  }
  return dict;
}
function sendJson() {
  var csrfToken = getCsrfToken();
  var xhr = new XMLHttpRequest();

  xhr.onload = () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      try {
        let response = JSON.parse(xhr.responseText);
        renderNatTables(response.dnat_rules || {}, response.snat_rules || {});
      } catch (error) {
        console.error(error);
      }
      return;
    }
    let message = "Unable to submit NAT rules.";
    try {
      let response = JSON.parse(xhr.responseText);
      if (response.error) {
        message = response.error;
      }
    } catch (error) {
      console.error(error);
    }
    alert(message);
  };

  xhr.onerror = () => alert("Unable to submit NAT rules.");
  xhr.open("POST", "/", true);
  xhr.setRequestHeader("Content-Type", "application/json; charset=UTF-8");
  xhr.setRequestHeader("X-CSRFToken", csrfToken);
  var j = tableToJson();
  console.log(j);
  xhr.send(JSON.stringify(j));
}

function getCsrfToken() {
  return document.querySelector('meta[name="csrf-token"]').getAttribute("content");
}

function requestJson(url, method, body) {
  var headers = { "Accept": "application/json" };
  if (method !== "GET") {
    headers["Content-Type"] = "application/json; charset=UTF-8";
    headers["X-CSRFToken"] = getCsrfToken();
  }

  return fetch(url, {
    method: method,
    headers: headers,
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : undefined,
  }).then(async function (response) {
    var data = {};
    try {
      data = await response.json();
    } catch (error) {
      console.error(error);
    }
    if (!response.ok) {
      throw new Error(data.error || "Request failed.");
    }
    return data;
  });
}

function selectControl(options, selectedValue, extraClass) {
  var select = document.createElement("select");
  select.name = "dropdown";
  select.className = extraClass || "select dropper";
  select.setAttribute("value", selectedValue);
  for (let optionData of options) {
    var option = document.createElement("option");
    option.value = optionData.value;
    option.textContent = optionData.label;
    if (optionData.value === selectedValue) {
      option.selected = true;
    }
    select.appendChild(option);
  }
  return select;
}

function snatInterfaceControl(selectedValue) {
  var selected = (selectedValue || "").trim();
  var options = snatInterfaceOptions.slice();
  var selectedKnown = options.some(function (option) {
    return option.value === selected;
  });

  if (selected && !selectedKnown) {
    options.unshift({ value: selected, label: selected + " (current)" });
  }
  if (!options.length) {
    options.push({ value: selected, label: selected || "No interfaces loaded" });
  }

  var select = selectControl(options, selected, "select dropper snat-interface-select");
  if (!selected && snatInterfaceOptions.length) {
    select.value = snatInterfaceOptions[0].value;
    select.setAttribute("value", select.value);
  }
  if (!snatInterfaceOptions.length && !selected) {
    select.disabled = true;
  }
  return select;
}

function snatInterfaceCell(selectedValue) {
  var cell = document.createElement("td");
  cell.appendChild(snatInterfaceControl(selectedValue));
  return cell;
}

function editableCell(value) {
  var cell = document.createElement("td");
  var div = document.createElement("div");
  div.contentEditable = "true";
  div.textContent = value;
  cell.appendChild(div);
  return cell;
}

function textCell(value) {
  var cell = document.createElement("td");
  var div = document.createElement("div");
  div.textContent = value;
  cell.appendChild(div);
  return cell;
}

function deleteCell() {
  var cell = document.createElement("td");
  var div = document.createElement("div");
  var button = document.createElement("button");
  button.type = "button";
  button.className = "btn btn-outline-danger btn-sm";
  button.textContent = "X";
  button.addEventListener("click", function () {
    deleteRule(button);
  });
  div.appendChild(button);
  cell.appendChild(div);
  return cell;
}

function renderNatTables(dnatRules, snatRules) {
  var dnatBody = dnatTable.getElementsByTagName("tbody")[0];
  var snatBody = snatTable.getElementsByTagName("tbody")[0];
  dnatBody.replaceChildren();
  snatBody.replaceChildren();

  for (let key of sortedObjectKeys(dnatRules)) {
    var rule = dnatRules[key];
    var dnatRow = document.createElement("tr");
    dnatRow.id = "dnat_row_" + key;
    dnatRow.appendChild(textCell(key));

    var protocolCell = document.createElement("td");
    protocolCell.appendChild(selectControl([
      { value: "tcp", label: "TCP" },
      { value: "udp", label: "UDP" },
    ], rule.protocol, "select dropper"));
    dnatRow.appendChild(protocolCell);

    dnatRow.appendChild(editableCell(rule.destination_port));
    dnatRow.appendChild(editableCell(rule.forward_ip));
    dnatRow.appendChild(editableCell(rule.forward_port));
    dnatRow.appendChild(deleteCell());
    dnatBody.appendChild(dnatRow);
  }

  for (let key of sortedObjectKeys(snatRules)) {
    var snatRule = snatRules[key];
    var snatRow = document.createElement("tr");
    snatRow.id = "snat_row_" + key;
    if (snatRule.probability) {
      snatRow.dataset.probability = snatRule.probability;
    }
    snatRow.appendChild(textCell(key));

    var snatProtocolCell = document.createElement("td");
    snatProtocolCell.appendChild(selectControl([
      { value: "all", label: "ALL" },
      { value: "tcp", label: "TCP" },
      { value: "udp", label: "UDP" },
    ], snatRule.protocol, "select dropper"));
    snatRow.appendChild(snatProtocolCell);

    var targetCell = document.createElement("td");
    targetCell.appendChild(selectControl([
      { value: "MASQUERADE", label: "MASQUERADE" },
      { value: "SNAT", label: "SNAT" },
    ], snatRule.target, "select dropper"));
    snatRow.appendChild(targetCell);

    snatRow.appendChild(editableCell(snatRule.source_ip));
    snatRow.appendChild(snatInterfaceCell(snatRule.output_interface));
    snatRow.appendChild(deleteCell());
    snatBody.appendChild(snatRow);
  }
}

function sortedObjectKeys(obj) {
  return Object.keys(obj || {}).sort(function (a, b) {
    var aNum = Number(a);
    var bNum = Number(b);
    if (!Number.isNaN(aNum) && !Number.isNaN(bNum)) {
      return aNum - bNum;
    }
    return a.localeCompare(b);
  });
}

function vnicElement(id) {
  return document.getElementById(id);
}

function setSnatInterfaceOptions(interfaces) {
  var seen = new Set();
  snatInterfaceOptions = [];
  for (let item of interfaces || []) {
    if (!item || !item.name || seen.has(item.name)) {
      continue;
    }
    seen.add(item.name);
    snatInterfaceOptions.push({
      value: item.name,
      label: item.name + (item.addresses && item.addresses.length ? " (" + item.addresses.join(", ") + ")" : ""),
    });
  }
  refreshSnatInterfaceCells();
}

function refreshSnatInterfaceCells() {
  if (!snatTable) {
    return;
  }
  var body = snatTable.getElementsByTagName("tbody")[0];
  if (!body) {
    return;
  }

  for (let row of body.rows) {
    if (!row.cells[4]) {
      continue;
    }
    var existingSelect = row.cells[4].querySelector("select");
    var selected = existingSelect ? existingSelect.value : row.cells[4].textContent.trim();
    row.replaceChild(snatInterfaceCell(selected), row.cells[4]);
  }
}

function setVnicStatus(message, isError) {
  var status = vnicElement("vnic-status");
  if (!status) {
    return;
  }
  status.textContent = message;
  status.className = isError ? "text-danger small" : "text-muted small";
}

function snatPoolPayloadFromForm() {
  var selectedIps = [];
  document.querySelectorAll(".snat-source-checkbox:checked").forEach(function (checkbox) {
    selectedIps.push(checkbox.value);
  });
  return {
    enabled: vnicElement("snat-pool-enabled").checked,
    interface: vnicElement("snat-pool-interface").value,
    source_ips: selectedIps,
  };
}

function renderVnicState(data) {
  var scan = data.scan || {};
  var pool = data.snat_pool || {};
  var capacity = data.capacity || {};
  var selectedIps = new Set(pool.source_ips || []);
  var sourceIps = scan.source_ips || [];
  var interfaces = scan.interfaces || [];
  var interfaceSelect = vnicElement("snat-pool-interface");
  var vnicList = vnicElement("vnic-list");

  setSnatInterfaceOptions(interfaces);

  if (!vnicList || !interfaceSelect) {
    return;
  }

  interfaceSelect.replaceChildren();
  var interfacePlaceholder = document.createElement("option");
  interfacePlaceholder.value = "";
  interfacePlaceholder.textContent = interfaces.length ? "Select interface" : "No interfaces";
  interfaceSelect.appendChild(interfacePlaceholder);
  for (let item of interfaces) {
    var interfaceOption = document.createElement("option");
    interfaceOption.value = item.name;
    interfaceOption.textContent = item.name + (item.addresses && item.addresses.length ? " (" + item.addresses.join(", ") + ")" : "");
    if (item.name === pool.interface) {
      interfaceOption.selected = true;
    }
    interfaceSelect.appendChild(interfaceOption);
  }

  vnicElement("snat-pool-enabled").checked = Boolean(pool.enabled);
  vnicElement("snat-pool-capacity").textContent = formatNumber(capacity.total_available_ports) +
    " ports across " + formatNumber(capacity.source_ip_count || 1) + " source IPs";

  vnicList.replaceChildren();
  if (!sourceIps.length) {
    var emptyRow = document.createElement("tr");
    var emptyCell = document.createElement("td");
    emptyCell.colSpan = 7;
    emptyCell.className = "text-muted";
    emptyCell.textContent = "Click Rescan VNICs after attaching or configuring secondary VNICs.";
    emptyRow.appendChild(emptyCell);
    vnicList.appendChild(emptyRow);
    setVnicStatus("No VNIC scan loaded.", false);
    return;
  }

  for (let ipInfo of sourceIps) {
    var row = document.createElement("tr");

    var useCell = document.createElement("td");
    var checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "form-check-input snat-source-checkbox";
    checkbox.value = ipInfo.ip;
    checkbox.checked = selectedIps.has(ipInfo.ip);
    checkbox.disabled = !ipInfo.configured;
    useCell.appendChild(checkbox);
    row.appendChild(useCell);

    var ipCell = document.createElement("td");
    ipCell.textContent = ipInfo.ip + (ipInfo.primary ? " primary" : "");
    row.appendChild(ipCell);

    var vnicCell = document.createElement("td");
    vnicCell.textContent = ipInfo.vnic_id || "-";
    row.appendChild(vnicCell);

    var interfaceCell = document.createElement("td");
    interfaceCell.textContent = ipInfo.interface || "-";
    row.appendChild(interfaceCell);

    var nicCell = document.createElement("td");
    nicCell.textContent = ipInfo.nic_index === undefined ? "-" : ipInfo.nic_index;
    row.appendChild(nicCell);

    var statusCell = document.createElement("td");
    statusCell.textContent = ipInfo.configured ? "Configured" : "Needs OS config";
    statusCell.className = ipInfo.configured ? "text-success" : "text-warning";
    row.appendChild(statusCell);

    var subnetCell = document.createElement("td");
    var matchedVnic = (scan.vnics || []).find(function (vnic) {
      return vnic.vnic_id === ipInfo.vnic_id;
    });
    subnetCell.textContent = matchedVnic ? (matchedVnic.subnet_cidr || "-") : "-";
    row.appendChild(subnetCell);

    vnicList.appendChild(row);
  }

  var scannedAt = scan.scanned_at ? formatDate(scan.scanned_at) : "-";
  setVnicStatus("Last scan: " + scannedAt, false);
}

function loadVnicState() {
  if (!vnicElement("vnic-panel")) {
    return;
  }
  requestJson("/api/vnics/status", "GET")
    .then(renderVnicState)
    .catch(function (error) {
      setVnicStatus(error.message, true);
    });
}

function rescanVnics() {
  setVnicStatus("Scanning attached VNICs...", false);
  requestJson("/api/vnics/rescan", "POST", {})
    .then(renderVnicState)
    .catch(function (error) {
      setVnicStatus(error.message, true);
      alert(error.message);
    });
}

function applySnatPool() {
  setVnicStatus("Applying SNAT source pool...", false);
  requestJson("/api/vnics/snat-pool", "POST", snatPoolPayloadFromForm())
    .then(function (data) {
      renderVnicState(data);
      renderNatTables(data.dnat_rules || {}, data.snat_rules || {});
      setVnicStatus("SNAT source pool applied.", false);
      loadDashboardStats();
    })
    .catch(function (error) {
      setVnicStatus(error.message, true);
      alert(error.message);
    });
}

function backupElement(id) {
  return document.getElementById(id);
}

function setBackupStatus(message, isError) {
  var status = backupElement("backup-status");
  if (!status) {
    return;
  }
  status.textContent = message;
  status.className = isError ? "text-danger small" : "text-muted small";
}

function backupPolicyFromForm() {
  return {
    auth_method: backupElement("backup-auth-method").value,
    region: backupElement("backup-region").value.trim(),
    compartment_id: backupElement("backup-compartment").value.trim(),
    namespace: backupElement("backup-namespace").value.trim(),
    bucket: backupElement("backup-bucket").value,
    prefix: backupElement("backup-prefix").value.trim(),
    enabled: backupElement("backup-enabled").checked,
    schedule: backupElement("backup-schedule").value,
    time_utc: backupElement("backup-time").value || "00:00",
    weekday: backupElement("backup-weekday").value,
    retention: backupElement("backup-retention").value || "30",
  };
}

function populateBackupPolicy(policy) {
  backupElement("backup-auth-method").value = policy.auth_method || "instance_principal";
  backupElement("backup-region").value = policy.region || "";
  backupElement("backup-compartment").value = policy.compartment_id || "";
  backupElement("backup-namespace").value = policy.namespace || "";
  backupElement("backup-prefix").value = policy.prefix || "ona-backups/";
  backupElement("backup-enabled").checked = Boolean(policy.enabled);
  backupElement("backup-schedule").value = policy.schedule || "manual";
  backupElement("backup-time").value = policy.time_utc || "00:00";
  backupElement("backup-weekday").value = policy.weekday || "0";
  backupElement("backup-retention").value = policy.retention || "30";
  setBucketOptions([], policy.bucket || "");
}

function setBucketOptions(buckets, selectedBucket) {
  var bucketSelect = backupElement("backup-bucket");
  if (!bucketSelect) {
    return;
  }
  bucketSelect.replaceChildren();

  var placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = buckets.length ? "Select a bucket" : "No buckets loaded";
  bucketSelect.appendChild(placeholder);

  var hasSelected = false;
  for (let bucket of buckets) {
    var option = document.createElement("option");
    option.value = bucket.name;
    option.textContent = bucket.name;
    if (bucket.name === selectedBucket) {
      option.selected = true;
      hasSelected = true;
    }
    bucketSelect.appendChild(option);
  }

  if (selectedBucket && !hasSelected) {
    var selectedOption = document.createElement("option");
    selectedOption.value = selectedBucket;
    selectedOption.textContent = selectedBucket;
    selectedOption.selected = true;
    bucketSelect.appendChild(selectedOption);
  }
}

function renderBackupList(backups) {
  var backupList = backupElement("backup-list");
  if (!backupList) {
    return;
  }
  backupList.replaceChildren();

  if (!backups || backups.length === 0) {
    var emptyRow = document.createElement("tr");
    var emptyCell = document.createElement("td");
    emptyCell.colSpan = 4;
    emptyCell.className = "text-muted";
    emptyCell.textContent = "No backups found for this bucket and prefix.";
    emptyRow.appendChild(emptyCell);
    backupList.appendChild(emptyRow);
    return;
  }

  for (let backup of backups) {
    var row = document.createElement("tr");

    var objectCell = document.createElement("td");
    objectCell.textContent = backup.name;
    row.appendChild(objectCell);

    var sizeCell = document.createElement("td");
    sizeCell.className = "text-end";
    sizeCell.textContent = formatBytes(backup.size);
    row.appendChild(sizeCell);

    var createdCell = document.createElement("td");
    createdCell.textContent = formatDate(backup.time_created || backup.time_modified);
    row.appendChild(createdCell);

    var actionCell = document.createElement("td");
    actionCell.className = "text-end";
    var restoreButton = document.createElement("button");
    restoreButton.type = "button";
    restoreButton.className = "btn btn-outline-primary btn-sm";
    restoreButton.textContent = "Restore";
    restoreButton.addEventListener("click", function () {
      restoreBackup(backup.name);
    });
    actionCell.appendChild(restoreButton);
    row.appendChild(actionCell);

    backupList.appendChild(row);
  }
}

function formatBytes(value) {
  var bytes = Number(value || 0);
  if (bytes < 1024) {
    return bytes + " B";
  }
  if (bytes < 1024 * 1024) {
    return (bytes / 1024).toFixed(1) + " KB";
  }
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  var date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function loadBackupState() {
  if (!backupElement("backup-panel")) {
    return;
  }
  setBackupStatus("Loading backup status...", false);
  requestJson("/api/backups/status", "GET")
    .then(function (data) {
      populateBackupPolicy(data.policy || {});
      renderBackupList(data.backups || []);
      if (data.error) {
        setBackupStatus(data.error, true);
      } else if (data.policy && data.policy.last_backup_error) {
        setBackupStatus("Last backup failed: " + data.policy.last_backup_error, true);
      } else if (data.policy && data.policy.last_backup_at) {
        setBackupStatus("Last backup: " + formatDate(data.policy.last_backup_at), false);
      } else {
        setBackupStatus("No backup has run yet.", false);
      }
    })
    .catch(function (error) {
      setBackupStatus(error.message, true);
    });
}

function refreshBuckets() {
  var policy = backupPolicyFromForm();
  var params = new URLSearchParams({
    auth_method: policy.auth_method,
    region: policy.region,
    compartment_id: policy.compartment_id,
    namespace: policy.namespace,
  });
  setBackupStatus("Loading buckets...", false);
  requestJson("/api/oci/buckets?" + params.toString(), "GET")
    .then(function (data) {
      if (data.namespace) {
        backupElement("backup-namespace").value = data.namespace;
      }
      setBucketOptions(data.buckets || [], policy.bucket);
      setBackupStatus("Buckets loaded.", false);
    })
    .catch(function (error) {
      setBackupStatus(error.message, true);
      alert(error.message);
    });
}

function saveBackupPolicy() {
  setBackupStatus("Saving backup policy...", false);
  requestJson("/api/backups/policy", "POST", backupPolicyFromForm())
    .then(function () {
      setBackupStatus("Backup policy saved.", false);
      loadBackupState();
    })
    .catch(function (error) {
      setBackupStatus(error.message, true);
      alert(error.message);
    });
}

function runBackupNow() {
  setBackupStatus("Creating backup...", false);
  requestJson("/api/backups/run", "POST", {})
    .then(function (data) {
      setBackupStatus("Backup created: " + data.backup.object_name, false);
      loadBackupState();
    })
    .catch(function (error) {
      setBackupStatus(error.message, true);
      alert(error.message);
    });
}

function restoreBackup(objectName) {
  if (!confirm("Restore NAT rules from this backup? Current ONA-managed rules will be replaced.")) {
    return;
  }
  setBackupStatus("Restoring backup...", false);
  requestJson("/api/backups/restore", "POST", { object_name: objectName })
    .then(function (data) {
      renderNatTables(data.dnat_rules || {}, data.snat_rules || {});
      setBackupStatus("Backup restored.", false);
    })
    .catch(function (error) {
      setBackupStatus(error.message, true);
      alert(error.message);
    });
}

function setText(id, value) {
  var element = document.getElementById(id);
  if (element) {
    element.textContent = value;
  }
}

function setProgress(id, value) {
  var element = document.getElementById(id);
  if (!element) {
    return;
  }
  var percent = Number(value || 0);
  percent = Math.max(0, Math.min(100, percent));
  element.style.width = percent + "%";
  element.setAttribute("aria-valuenow", percent);
}

function formatPercent(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return Number(value).toFixed(1) + "%";
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function formatRateBytes(value) {
  return formatBytes(value || 0) + "/s";
}

function formatRatePackets(value) {
  return Number(value || 0).toFixed(1) + " pkt/s";
}

function renderDashboardStats(data) {
  var cpuPercent = data.cpu ? data.cpu.percent : null;
  var memory = data.memory || {};
  var nat = data.nat || {};
  var network = data.network || {};
  var rates = network.rates || {};
  var rules = data.rules || {};

  setText("metric-cpu-percent", formatPercent(cpuPercent));
  setText("metric-cpu-load", data.cpu && data.cpu.load_average && data.cpu.load_average.length
    ? "Load " + data.cpu.load_average.join(" / ")
    : "Load -");
  setProgress("metric-cpu-bar", cpuPercent || 0);

  setText("metric-memory-percent", formatPercent(memory.percent));
  setText("metric-memory-detail", formatBytes(memory.used_bytes) + " / " + formatBytes(memory.total_bytes));
  setProgress("metric-memory-bar", memory.percent || 0);

  setText("metric-ports-used", formatNumber(nat.ports_in_use) + " used");
  setText("metric-ports-detail", formatNumber(nat.available_ports) + " available of " +
    formatNumber(nat.total_available_ports) + " across " + formatNumber(nat.snat_source_ip_count || 1) + " IPs");
  setProgress("metric-ports-bar", nat.port_utilization_percent || 0);

  setText("metric-connections-total", formatNumber(nat.total_connections));
  setText("metric-conn-rate", Number(nat.connections_per_second || 0).toFixed(2) + " conn/s");
  setProgress("metric-connections-bar", nat.connection_utilization_percent || 0);

  setText("metric-throughput-bytes", formatRateBytes(rates.total_bytes_per_second));
  setText("metric-throughput-detail", "RX " + formatRateBytes(rates.rx_bytes_per_second) + " / TX " + formatRateBytes(rates.tx_bytes_per_second));
  setText("metric-throughput-packets", formatRatePackets(rates.total_packets_per_second));
  setText("metric-rule-counts", "DNAT " + formatNumber(rules.dnat) + " / SNAT " + formatNumber(rules.snat));
  setText("metric-updated", formatDate(data.timestamp));
}

function loadDashboardStats() {
  if (!document.getElementById("stats-panel")) {
    return;
  }
  requestJson("/api/dashboard/stats", "GET")
    .then(renderDashboardStats)
    .catch(function (error) {
      setText("metric-updated", error.message);
    });
}

function startDashboardPolling() {
  if (dashboardPollTimer) {
    return;
  }
  loadDashboardStats();
  dashboardPollTimer = window.setInterval(loadDashboardStats, 30000);
}

function startDashboardStream() {
  if (!document.getElementById("stats-panel")) {
    return;
  }
  if (!window.EventSource) {
    startDashboardPolling();
    return;
  }

  var source = new EventSource("/api/dashboard/stream");
  source.onmessage = function (event) {
    try {
      renderDashboardStats(JSON.parse(event.data));
    } catch (error) {
      console.error(error);
    }
  };
  source.onerror = function () {
    source.close();
    startDashboardPolling();
  };
}
