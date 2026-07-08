function toggleSidebar(){

    document
        .getElementById(
            "mobileSidebar"
        )
        .classList
        .toggle(
            "show-sidebar"
        );

    document
        .getElementById(
            "sidebarOverlay"
        )
        .classList
        .toggle(
            "show-overlay"
        );

}

/* ================= Account Dropdown Menu ================= */

function toggleProfileMenu(event){

    event.stopPropagation();

    const dropdown = document.getElementById("profileDropdown");

    if(dropdown){
        dropdown.classList.toggle("show-menu");
    }

}

document.addEventListener("click", function(event){

    const dropdown = document.getElementById("profileDropdown");

    if(dropdown && dropdown.classList.contains("show-menu")){

        if(!dropdown.contains(event.target)){
            dropdown.classList.remove("show-menu");
        }

    }

});

/* ================= Manage Budget Modal ================= */

function openBudgetModal(){

    const overlay = document.getElementById("budgetModalOverlay");

    if(overlay){
        overlay.classList.add("show-modal");
    }

}

function closeBudgetModal(){

    const overlay = document.getElementById("budgetModalOverlay");

    if(overlay){
        overlay.classList.remove("show-modal");
    }

}