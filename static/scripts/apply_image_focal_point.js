function apply_image_focal_point(image_id, focus) {
    x_percent = (parseFloat(focus.x) + 1.0) * 50;
    y_percent = (2-(parseFloat(focus.y) + 1.0)) * 50;
    document.getElementById(image_id).style.objectPosition = `${x_percent}% ${y_percent}%`
}