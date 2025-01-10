const compressImage = async (file, { quality = 1, type = file.type }) => {
    console.log("launching image compressor")
    // Get as image data
    const imageBitmap = await createImageBitmap(file);

    let scale = 1000 / imageBitmap.width;
    if (scale>1) {
        scale = 1;
    }

    // Draw to canvas
    const canvas = document.createElement('canvas');
    canvas.width = imageBitmap.width * scale;
    canvas.height = imageBitmap.height *scale;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(imageBitmap, 0, 0, canvas.width,canvas.height);

    // Turn into Blob
    const blob = await new Promise((resolve) =>
        canvas.toBlob(resolve, type, quality)
    );

    // Turn Blob into File
    return new File([blob], file.name, {
        type: blob.type,
    });
};

async function triggerCompression() {
    //alert("ededed")
    let input = document.getElementById("image_upload_button");
    let files = input.files;
    // No files selected
    if (!files.length) return;

    // We'll store the files in this data transfer object
    const dataTransfer = new DataTransfer();

    // For every file in the files list
    for (const file of files) {
        // We don't have to compress files that aren't images
        if (!file.type.startsWith('image')) {
            // Ignore this file, but do add it to our result
            dataTransfer.items.add(file);
            continue;
        }

        // We compress the file by 50%
        const compressedFile = await compressImage(file, {
            quality: 0.5,
            type: 'image/jpeg',
        });

        // Save back the compressed file instead of the original file
        dataTransfer.items.add(compressedFile);
        console.log("image compress");
    }

    // Set value of the file input to our new files list
    console.log(input.files[0].size);
    input.files = dataTransfer.files;
    console.log(input.files[0].size);
    console.log(input.files[0]);
    document.getElementById("title_image").src = URL.createObjectURL(input.files[0]);
    document.getElementById("title_image_description").style.display = "block";
    document.getElementById("title_image").addEventListener("click", e => {
        const mid_x = e.target.width / 2;
        const mid_y = e.target.height / 2;
        console.log(e);
        x_pos = e.x-e.target.x;
        y_pos = e.y-e.target.y;

        focal_point_x = (x_pos-mid_x)/mid_x;
        focal_point_y = -(y_pos-mid_y)/mid_y;

        console.log(focal_point_x, focal_point_y);
        document.getElementById("focus_x").value = focal_point_x;
        document.getElementById("focus_y").value = focal_point_y;    
    })
}
