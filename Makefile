clean:
	rm -rf build dist

build: clean
	pip wheel -w dist --no-deps .

publish: build
	twine upload dist/*
