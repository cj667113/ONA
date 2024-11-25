let ruleType = "dnat";
let dnatButton = document.getElementById("dnat-btn");
let snatButton = document.getElementById("snat-btn");
let bottomContainer = document.getElementById("bottom-container");
let dnatTable = document.getElementById("dnat-table");
let snatTable = document.getElementById("snat-table");
let tempDeleteButton = document.getElementById("temp-delete-btn");
let tempDropDown = document.getElementById("temp-dropdown");
let tempDropDownSNAT = document.getElementById("temp-dropdown-2");

console.log("V1.6.1 Loaded");

function updateDropDowns() {
  //console.log("Updating Dropdowns");
  var dropdowns = document.getElementsByClassName('select');
  for (var obj of dropdowns) {
    if (obj.className === 'select') {
      var options = obj.children;
      //console.log("Object Dropdown" + obj);
      for (child of options) {
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
  const selectElement = document.querySelector(".select");

  //Default the correct drop-down selection for protocol
  updateDropDowns();

  //Update select element value when selection changes
  $(document).on('change', '.dropper', function () {
    //console.log("Dropdown changing.");
    //alert($(this).val());
    $(this).attr("value", $(this).val());
    //console.log($(this).val());
  });

  // selectElement.addEventListener("change", (event) => {
  //   //console.log(`${event.target.value}`);
  // })





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

    bottomContainer.className = "container";
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

    bottomContainer.className = "container";
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

  var cloned_dropdown_snat = tempDropDown.cloneNode(true);
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
  cell4.innerHTML = "<div contenteditable>-</div>";
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

  for (var i = 0; i < table_dnat.rows.length; i++) {
    var tableRow = table_dnat.rows[i];
    var rowData = [];
    for (var j = 0; j < tableRow.cells.length; j++) {
      if (j === 1) {
        try {
          setData = tableRow.cells[j].querySelector(".select").getAttribute('value');
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
      if (f === 1 || f === 2) {
        try {
          console.log("SetData: " + tableRow.cells[f].querySelector(".select").getAttribute('value'));
          setData = tableRow.cells[f].querySelector(".select").getAttribute('value');
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
    dict[[dn][0]] = predict;
    d++;
  }
  return dict;
}
function sendJson() {
  responseText = document.getElementById("response");
  var xhr = new XMLHttpRequest();

  xhr.onload = (res) => {
    //console.log(res);

    //Force app.js to refresh rather than parsing new html
    location.reload();

    //responseText.innerHTML = res["target"]["response"];
  };

  let form = document.forms[0];
  xhr.open("POST", "/", true);
  xhr.setRequestHeader("Content-Type", "application/json; charset=UTF-8");
  var j = tableToJson();
  console.log(j);
  xhr.send(JSON.stringify(j));
}


