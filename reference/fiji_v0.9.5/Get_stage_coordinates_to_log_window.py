#@ String file
#@ Integer nrTiles

from ij import IJ
from loci.plugins.in import ImporterOptions
from loci.formats import ImageReader
from loci.formats import MetadataTools

options = ImporterOptions()
options.setId(file)

# parse metadata
reader = ImageReader()
omeMeta = MetadataTools.createOMEXMLMetadata()
reader.setMetadataStore(omeMeta)
reader.setId(file)
seriesCount = reader.getSeriesCount()
#IJ.log(str(seriesCount))

#Overwrite nrTiles if passed as argument (not -1)
if nrTiles != -1:
	seriesCount = nrTiles
reader.close()
posX = [(omeMeta.getPlanePositionX(i,0).value()) for i in range(seriesCount)]
posY = [(omeMeta.getPlanePositionY(i,0).value()) for i in range(seriesCount)]
#IJ.log(str(pos))

for i in range(seriesCount):
	IJ.log(str(posX[i]))
	IJ.log(str(posY[i]))
