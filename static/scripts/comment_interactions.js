function show_hide_interactions(uid) {
    element = document.getElementById(`reply-${uid}`);
    if (element.style.display == "none") {
        element.style.display = "block";
    } else {
        element.style.display = "none"
    }
}