clean:
	rm -rf build dist

build: clean
	uv build

publish: build
	uv publish
