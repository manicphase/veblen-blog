function body_changed() {
    title_input = document.getElementById("title_input");
    body_input = document.getElementById("body_input");    
    if (body_input.scrollHeight>200) {
        body_input.style.height = body_input.scrollHeight;
    }
    preview_content = document.getElementById("preview_content");
    preview_content.innerHTML = `<h1>${title_input.value}</h1>
                                        ${body_input.value}`
}

document.getElementById("title_image").addEventListener("click", e => {
    console.log(e);
})