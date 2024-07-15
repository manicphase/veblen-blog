//input.addEventListener('change', (e) => {console.log("wait a minute")})

console.log("SCRIPT LOADED")


const compressImage = async (file, { quality = 1, type = file.type }) => {
    console.log("launching image compressor")
    // Get as image data
    const imageBitmap = await createImageBitmap(file);

    const scale = 1000 / imageBitmap.width;
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
    document.getElementById("compressed_image").src = URL.createObjectURL(input.files[0]);
    document.getElementById("compressed_title_image").files = input.files;
    input.value = "";
}
