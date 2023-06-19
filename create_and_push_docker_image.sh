tag=${1}
operator_image="${operator_image:-quay.io/domino/extendedapi}"
docker build -f ./Dockerfile -t ${operator_image}:${tag} .
docker push ${operator_image}:${tag}