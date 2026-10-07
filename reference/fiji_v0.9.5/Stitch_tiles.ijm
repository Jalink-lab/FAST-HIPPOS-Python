//Macro to stitch tiles without overlap.
//For Leica files the stage coordinates of the tiles are written into the metadata of the output .tif file, as well as the grid layout, the tile size and the overlap (manual entry)

#@ File (label = "Input folder", style = "directory") inputFolder
#@ File (label = "Output folder", style = "directory") outputFolder
#@ String (choices={"Get grid layout from LIF file", "Manually enter grid layout (below)"}, style="list") GridLayout_choice
#@ Double (label = "Overlap between tiles (%)", value=0) overlap
#@ File (label = "LIF file containing tile positions", style = "file") lifFile
#@ Integer (label = "Grid layout: nr of X tiles", min=0, value=0) gridSizeX
#@ Integer (label = "Grid layout: nr of Y tiles", min=0, value=0) gridSizeY
#@ Boolean(label="Correct pixelsize (fix for Leica misinterpretation)", value=true) correctPixelSize

setBatchMode(true);
list = getFileList(inputFolder);
setOption("ExpandableArrays", true);
imageList = newArray();
k=0;
for (i=0; i<list.length; i++) {
	if(endsWith(list[i], ".tif")) {
		imageList[k] = list[i];
		k++;
	}
}
imageList = Array.sort(Array.trim(imageList, k));
name = File.getNameWithoutExtension(imageList[0]);
extension = substring(imageList[0], lastIndexOf(imageList[0], "."));

numberOfDigits = lengthOf(toString(imageList.length));
iString = "";
for (i = 0; i < numberOfDigits; i++) iString += "i";		//'i', 'ii', or 'iii', etc.

tileString = "{" + iString + "}";
tileBaseName = name.substring(0, name.length - numberOfDigits);
firstTileNr = substring(name, tileBaseName.length, name.length);

//Get some info from the first tile
open(inputFolder + File.separator + imageList[0]);
getDimensions(width, height, channels, slices, frames);
getVoxelSize(pixelWidth, pixelHeight, pixelDepth, unit);
if(correctPixelSize) {
	pixelWidth = (width-1)/width*pixelWidth;
	pixelHeight = (height-1)/height*pixelHeight;
	setVoxelSize(pixelWidth, pixelHeight, pixelDepth, unit);
}
interval = Stack.getFrameInterval();
close();

if(GridLayout_choice == "Get grid layout from LIF file") {
	stagePositions = getStagePositions(lifFile, imageList);
	layout = find_tile_layout(stagePositions);
	gridSizeX = layout[0];
	gridSizeY = layout[1];
}

if(overlap>=0) run("Grid/Collection stitching", "type=[Grid: snake by rows] order=[Right & Down                ] grid_size_x="+gridSizeX+" grid_size_y="+gridSizeY+" tile_overlap="+overlap+" first_file_index_i="+firstTileNr+" directory=["+inputFolder+"] file_names=["+tileBaseName + tileString + extension+"] output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display] use");
else run("Grid/Collection stitching", "type=[Grid: snake by rows] order=[Left & Down] grid_size_x="+gridSizeX+" grid_size_y="+gridSizeY+" tile_overlap="+overlap+" first_file_index_i="+firstTileNr+" directory=["+inputFolder+"] file_names=["+tileBaseName + tileString + extension+"] output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display] use");
setVoxelSize(pixelWidth, pixelHeight, pixelDepth, unit);
Stack.setXUnit("um");
Stack.setFrameInterval(interval);
if(GridLayout_choice == "Get grid layout from LIF file") {
	setMetadata("info", "Stitched image with tile layout:\n"+gridSizeX+","+gridSizeY+"\nStage coordinates:\n"+arrayToString(stagePositions, ",")+"\nTile size (um):\n"+(width)*pixelWidth+","+(height)*pixelHeight+"\n"+"overlap (%):\n"+overlap+"\n");
	if(!correctPixelSize) setMetadata("info", "Stitched image with tile layout:\n"+gridSizeX+","+gridSizeY+"\nStage coordinates:\n"+arrayToString(stagePositions, ",")+"\nTile size (um):\n"+(width-1)*pixelWidth+","+(height-1)*pixelHeight+"\n"+"overlap (%):\n"+overlap+"\n");	//Why (width-1)? Because somehow the pixel size from the .lif file is wrongly calculated!

	metadata = split(getMetadata("Info"), "\n");
	coords = split(metadata[3], ",");
	print(coords.length+" coordinates (x and y) for "+gridSizeX*gridSizeY+" tiles written to the metadata.");
	if(2*gridSizeX*gridSizeY != coords.length) showMessage("WARNING! "+coords.length+" coordinates written, where it should be "+2*gridSizeX*gridSizeY);
}
else setMetadata("info", "Stitched image with tile layout:\n"+gridSizeX+","+gridSizeY+"\n");

setBatchMode("show");
saveAs("Tiff", outputFolder + File.separator + substring(tileBaseName, 0, tileBaseName.length-2) + "_STITCHED.tif");	//subtract 2 characters, because the tile names start with '_s'


function getStagePositions(lifFile, imageList) {
	//Get stage coordinates of all the tiles. N.B. Counting always starts at the first tile in the .lif file.
	print("\\Clear");
	run("Get stage coordinates to log window", "file=["+lifFile+"], nrtiles="+imageList.length);	//Run a Jython script to print the stage coordinates to the log window
	logWindow = getInfo("log");
	stagePositions = split(logWindow, "\n");
	print("\\Clear");
	print("Found stage coordinates");
	return stagePositions;
}

//Find Tile layout from stage positions. Returns an array (tilesX, tilesY).
function find_tile_layout(stagePositions) {
	tilesX = 1;
	tilesY = 1;
	yPos = newArray(stagePositions.length/2);
	xPos = newArray(stagePositions.length/2);

	for(i=0; i<xPos.length; i++) {
		if(i>0) { if(!occursInArray(yPos, stagePositions[2*i])) tilesY++; }
		if(i>0) { if(!occursInArray(xPos, stagePositions[2*i+1])) tilesX++; }
		yPos[i] = stagePositions[2*i];
		xPos[i] = stagePositions[2*i+1];
	}
	print("Found grid layout: "+tilesX+" x "+tilesY);
	return newArray(tilesX, tilesY);
}

function occursInArray(array, value) {
	for(i=0; i<array.length; i++) {
		if(array[i] == value) return true;
	}
	return false;
}

//Converts an array into a string, elements separated by 'separator'
function arrayToString(array, separator) {
	outputString = "";
	for (i = 0; i < array.length; i++) {
		outputString += toString(array[i]) + separator;
	}
	return substring(outputString, 0, outputString.length - separator.length);
}
